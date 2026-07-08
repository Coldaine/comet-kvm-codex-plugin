# Plan 01: VLM-MCP Integration & Safe Agent-Driven Architecture

## 1. Context and Goals
The original implementation had an architectural contradiction: it defined a "Three-Agent Topology" but buried the VLM client inside a monolithic Python state machine (`StatefulBiosRuntime`), executing direct API calls out-of-band of the MCP protocol. 

This plan establishes the correct, decoupled architecture:
1. **Stateless MCP Tools**: The MCP server exposes modular tools for hardware actions, VLM perception, and local matching.
2. **LLM Driver as the Orchestrator**: The Driver Agent (the orchestrating LLM) manages the stateful crawl stack, path navigation, and policy verification loops.
3. **Transparent VLM Integration**: The VLM is invoked strictly via an MCP tool call (`kvm_vlm_parse`), ensuring all screenshots, prompts, and output JSON parses are recorded in the MCP server's transaction log.
4. **Direct Value Mutation**: We do not parse or enumerate dropdown options. For target BIOS tuning (MSI Z690), settings are mutated by navigating to the row and typing the numeric value (e.g. PL1, CPU Lite Load Mode number) directly.

---

## 2. Exposing the VLM Perception Tool

We will register the VLM client as a formal MCP tool in `glkvm_mcp.py`.

### Tool Signature
```python
@mcp.tool(name="kvm_vlm_parse", annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True})
async def kvm_vlm_parse(screenshot_path: str, previous_state_id: Optional[str] = None, last_action: Optional[str] = None) -> dict:
    """
    Parse a saved BIOS screenshot using the VLM (GPT-4o/Gemini) and return a structured JSON description.
    Accepts a local screenshot cache path to optimize stdio payload sizes.
    """
```

### Local Verification Tool (VLM-Bypass)
To prevent latency and token waste during intermediate navigation hops, we expose a local verification tool:
```python
@mcp.tool(name="kvm_match_screen", annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True})
async def kvm_match_screen(screenshot_path: str, expected_node_id: str) -> dict:
    """
    Verify if the captured screenshot matches a known node in the state graph
    using local perceptual hashing and OCR fingerprinting (no VLM API call).
    """
```

---

## 3. Safe Setting Mutation Workflow

Instead of granular tools like `bios_navigate_to` and `bios_apply_setting_change`, we consolidate mutation into a single stateful, policy-gated entry point:

```python
@mcp.tool(name="bios_set_setting", annotations={"readOnlyHint": False, "destructiveHint": True})
async def bios_set_setting(capability_id: str, desired_value: str, approval_id: Optional[str] = None) -> dict:
    """
    Propose or apply a setting modification. Navigates, mutates, and verifies internally.
    If called without a verified approval_id for protected settings, returns a human-approval token.
    """
```

### Mutation Execution Details
1. **Navigate**: The sidecar uses the stored graph to navigate to the target setting row.
2. **Direct Typing**: It presses `"Enter"` or clears the field, types the `desired_value` directly using text input (e.g. typing `"125"` for PL1 or `"9"` for CPU Lite Load), and presses `"Enter"`. No option list enumeration is performed.
3. **Grounding Verification**: It captures a post-mutation screenshot and calls `kvm_vlm_parse` to confirm the value next to the label matches `desired_value`.

---

## 4. Implementation Steps

* **Phase 1: Cleanup (Completed)**: Remove superseded drafts and update references.
* **Phase 2: Bug Fixes**: Correct the async threading crash in `observe.py` where `asyncio.to_thread` wraps the async `parse_screenshot` method.
* **Phase 3: Tool Implementation**: Expose the namespaced raw tools (`comet.raw.*`), the `kvm_vlm_parse` tool, the local `kvm_match_screen` tool, and the unified `bios_set_setting` tool.
* **Phase 4: Test Expansion**: Add tests in `tests/` validating VLM JSON payloads and the `bios_set_setting` execution paths.
