# Plan 01: VLM-MCP Boundary Integration & Safety Plan

## 1. Context and Goals
Currently, the Vision-Language Model (VLM) perception client is called as an out-of-band side-channel (via direct Python imports) inside the sidecar runtime. This creates a disconnect: the MCP server cannot see, log, or audit what the VLM receives or returns. Furthermore, a critical async threading bug makes this flow unusable in production.

This plan establishes the correct architecture by:
1. **Refactoring the VLM into a formal MCP Tool** (`kvm_vlm_parse` / `bios_vlm_parse`).
2. **Integrating VLM transaction auditing** directly into the unified MCP command and log streams.
3. **Fixing the critical async threading bug** in the observation pipeline.
4. **Implementing VLM-bypass caching** via local OCR and perceptual hashing to minimize API usage.

---

## 2. Refactoring the VLM to an MCP Tool

We will expose the VLM perception service as a formal tool on the FastMCP server in `glkvm_mcp.py`.

### Tool Signature
```python
@mcp.tool(name="kvm_vlm_parse", annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True})
async def kvm_vlm_parse(screenshot_path: str, previous_state_id: Optional[str] = None, last_action: Optional[str] = None) -> dict:
    """
    Parse a BIOS screenshot using the VLM (GPT-4o) and return a structured JSON description.
    Supports token tracking, auditing, and corrective retries.
    """
```

### Benefits of the Tool Boundary
* **Visibility**: Every VLM request and response is visible to the orchestrating agent and fully recorded in the MCP server's transaction logs.
* **Separation of Concerns**: The VLM tool retrieves the screenshot file from the local cache and runs the parsing, isolating the API transport layer from the core state/navigation engine.
* **Swappability**: The VLM backend can be easily updated or routed to different APIs without editing the core sidecar logic.

---

## 3. Resolving Implementation Bugs & Limitations

### Fix the Async Threading Bug
In `src/bios_sidecar/controller/observe.py` lines 58–63:
```diff
-        vlm_res = await asyncio.to_thread(
-            self.vlm_client.parse_screenshot,
-            img_bytes,
-            previous_state=prev_dict,
-            last_action=last_action,
-        )
+        vlm_res = await self.vlm_client.parse_screenshot(
+            img_bytes,
+            previous_state=prev_dict,
+            last_action=last_action,
+        )
```
* **Why**: `parse_screenshot` is an `async def` function. Passing it to `asyncio.to_thread` is a syntax error that returns a coroutine object without executing it, crashing the pipeline.

### Redesigning Mutation Options Selection
To fix the issue where `BiosMutator` cannot find option lists because they are hidden inside popup modals:
1. **Interactive Options Probing**: If `cursor_ctrl.options` is empty, the mutator will:
   * Press `Enter` to open the dropdown modal.
   * Call `observe_state` (which captures the screenshot and invokes the VLM parser).
   * The VLM will parse the modal options visible on the screen.
   * The mutator calculates the `ArrowDown`/`ArrowUp` steps from the modal options.
   * Send the target selections, then press `Enter` to confirm.

---

## 4. Implementation Phase Order

### Phase 1: Documentation and Cleaning (This PR)
* Delete the superseded `bios-cartography.md` design draft.
* Update `skills/comet-bios-triage/SKILL.md` and `docs/architecture.md` to remove historical references.
* Commit the VLM-MCP integration plan in `docs/plans/`.

### Phase 2: Bug Fixes & Tool Registration
* Patch the async threading bug in `observe.py`.
* Implement and register the `kvm_vlm_parse` tool in `glkvm_mcp.py`.

### Phase 3: local OCR/Phash Bypass
* Refactor `StateObserver.observe_state` to call `StateMatcher` using OCR/visual hashes *before* calling the VLM tool. If matched, skip the VLM call and load the cached state node.
