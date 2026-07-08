# Plan 01: VLM-MCP Integration & Safe Agent-Driven Architecture

## 1. Context and Goals
The original implementation had an architectural contradiction: it defined a "Three-Agent Topology" but buried the VLM client inside a monolithic Python state machine (`StatefulBiosRuntime`), executing direct API calls out-of-band of the MCP protocol. 

This plan establishes the correct, decoupled architecture:
1. **Stateless MCP Tools**: The MCP server exposes modular tools for KVM actions, VLM perception, and local matching.
2. **LLM Driver as the Orchestrator**: The Driver Agent (the orchestrating LLM) manages the stateful crawl stack, path navigation, and policy verification loops.
3. **Transparent VLM Integration**: The VLM is invoked strictly via an MCP tool call (`kvm_vlm_parse`), ensuring all screenshots, prompts, and output JSON parses are recorded in the MCP server's transaction log.
4. **Balanced Tool Granularity**: We avoid over-collapsing the stateful tools to ensure we don't hold the active KVM session hostage during human approvals, and we retain modular navigation and observation capabilities.

---

## 2. Exposing the VLM Perception & Matching Tools

We will register the VLM client and local matching logic as formal MCP tools in `glkvm_mcp.py`.

### Tool Signatures
```python
@mcp.tool(name="kvm_vlm_parse", annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True})
async def kvm_vlm_parse(screenshot_path: str, previous_state_id: Optional[str] = None, last_action: Optional[str] = None) -> dict:
    """
    Parse a saved BIOS screenshot using the VLM (GPT-4o/Gemini) and return a structured JSON description.
    Accepts a local screenshot cache path to optimize stdio payload sizes.
    """

@mcp.tool(name="kvm_match_screen", annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True})
async def kvm_match_screen(screenshot_path: str, expected_node_id: str) -> dict:
    """
    Verify if the captured screenshot matches a known node in the state graph
    using local perceptual hashing and OCR fingerprinting (no VLM API call).
    """
```

---

## 3. Stateful MCP Tool Surface

We expose the stateful BIOS capabilities to the Driver Agent through the following distinct, policy-gated tools:

### Session & Observation
* **`bios_connect(host, password, username)`**: Starts the run session.
* **`bios_disconnect()`**: Closes the session and releases resources.
* **`bios_observe_state()`**: Captures the screen, performs local matching (calling `kvm_vlm_parse` only if unmatched), and returns the current `BiosState`.

### Navigation & Exploration
* **`bios_navigate_to(target_node_id)`**: Navigates along the graph to the target screen using local OCR/phash verification (`kvm_match_screen`) at each intermediate hop to ensure zero drift without VLM overhead.
* **`bios_crawl_step()` / `bios_crawl_region()`**: Exposes incremental and full DFS crawling for map generation.

### Setting Mutation & Safety
* **`bios_propose_setting_change(capability_id, desired_value)`**: Offline validation and policy gate. Evaluates risks and registers a plan to get the `approval_id` upfront, without holding the KVM screen hostage.
* **`bios_apply_setting_change(plan_id, approval_id, capability_id, desired_value)`**: Performs the actual mutation and verification once approval is verified.
  * *Interaction details*: Navigates to the row, presses Enter, types the value directly (e.g. typing `"125"` for PL1 or `"9"` for CPU Lite Load), hits Enter, and calls `kvm_vlm_parse` to verify the setting has updated.
* **`bios_save_and_reboot(approval_id)`**: Navigates to save, verifies the confirmation dialog via the VLM tool, and reboots.
* **`bios_abort_and_recover()`**: Safety recovery (releases keys, backs out of modals).

---

## 4. Implementation Steps

* **Phase 1: Cleanup (Completed)**: Remove superseded drafts and update references.
* **Phase 2: Bug Fixes**: Correct the async threading crash in `observe.py` where `asyncio.to_thread` wraps the async `parse_screenshot` method.
* **Phase 3: Tool Implementation**: Expose the namespaced raw tools (`comet.raw.*`), the `kvm_vlm_parse` tool, the local `kvm_match_screen` tool, and the stateful `bios_*` tools.
* **Phase 4: Test Expansion**: Add tests in `tests/` validating VLM JSON payloads and the `bios_set_setting` execution paths.
