# Plan 01: VLM-MCP Integration & Safe Agent-Driven Architecture

> **Status:** Active
> **Supersedes:** the monolithic in-process VLM design and the collapsed 5-tool surface.

## 1. Context and Goals

The original implementation had an architectural contradiction: it defined a "three-agent topology" but buried the VLM client inside a monolithic Python state machine (`StatefulBiosRuntime`), executing direct API calls out-of-band of the MCP protocol.

This plan establishes the correct, phase-preserving architecture:

1. **Phase-preserving stateful tool surface.** The MCP server exposes a compact but modular set of `bios_*` tools that keep the operational seams — observe, crawl, navigate, propose, apply, save, recover, trace — distinct. Not one giant `bios_set_setting`; not raw HID everywhere.
2. **Stateful position tracker inside the sidecar.** Because the BIOS has no accessibility tree, the sidecar maintains a stateful representation of where the cursor is in the menu tree, backed by the state graph. The driver agent calls semantic tools; it never drives raw keys.
3. **Transparent, tool-driven VLM perception.** The VLM is invoked strictly via an MCP tool call (`kvm_vlm_parse`), so every screenshot, prompt, and parsed JSON is recorded in the MCP transaction log. The VLM is a fast, audited perception *service*, not a chat peer.
4. **Out-of-band human approval.** The driver agent proposes a change and halts. A human grants approval out-of-band. The driver never self-approves.

---

## 2. The Three-Tier Tool Hierarchy

### Tier 1 — Driver-agent tools (the normal happy path)

Semantic, stateful, policy-gated. This is the surface the tuning/triage agent uses.

| Tool | Purpose |
|------|---------|
| `bios_connect(host, password, username)` | Open Comet/session/run context. |
| `bios_observe_state()` | Grounding/sync entry point. Captures screen, local-matches, calls VLM only when unmatched. |
| `bios_crawl_region(scope, max_depth, stop_on_hazard)` | Supervised BIOS enumeration/cartography (DFS). |
| `bios_navigate_to(target)` | Deterministic path replay to a node/capability, with local hash verification per hop. |
| `bios_propose_setting_change(capability_id, desired_value)` | Register plan, return approval requirement. Machine stays idle/safe. |
| `bios_apply_setting_change(plan_id, approval_id)` | Execute a pre-approved staged mutation. Stages the value; does not commit to NVRAM. |
| `bios_save_and_reboot(approval_id)` | Policy-gated F10 → VLM-verify confirm dialog → commit → track reboot. |
| `bios_abort_and_recover()` | Safety escape hatch (release keys, Escape back-out). |
| `bios_export_trace()` | Evidence and replay as first-class output. |
| `bios_disconnect()` | Lifecycle teardown. |

### Tier 2 — Inspection / debug (callable, but not the happy path)

Exposed primarily as MCP **resources** rather than task tools:

- `bios://state/current`, `bios://graph/current`, `bios://capabilities/current`, `bios://policy/current`
- `bios_crawl_step()` — single-step crawl for interactive debugging.

### Tier 3 — Internal / admin (segregated, gated)

Raw HID and perception primitives. Not part of the normal BIOS automation surface.

| Tool | Purpose |
|------|---------|
| `kvm_vlm_parse(screenshot_ref, previous_state_id?, last_action?)` | Audited VLM perception. Called by the sidecar; optionally callable for debug. |
| `kvm_match_screen(screenshot_ref, expected_node_id)` | Local phash/OCR match (no VLM). VLM-bypass optimization. |
| `comet_raw_send_keys`, `comet_raw_screenshot`, `comet_raw_mouse_*`, `comet_raw_status` | Raw HID/capture. Debug/admin only. Legacy `kvm_*` names are aliases pending migration. |
| `comet_atx_power`, `comet_atx_click` | Power/reset via ATX board. |
| `comet_msd_upload` | On-device persistence to `/userdata/media/`. |
| `comet_sysinfo` | Device metadata. |

> **Note on approval:** `bios_grant_human_approval` is **not** a Tier 1 driver tool. Approval is granted out-of-band (operator UI or direct store write). The driver polls approval status; it must not approve itself.

---

## 3. VLM Perception Service

### 3.1 Framework decision: `instructor` + `litellm`

We do **not** roll our own VLM transport or JSON-repair logic. See `docs/decisions.md` D10.

- **`litellm`** — one interface across providers. Lets us route to **OpenRouter vision models** (e.g. `openrouter/qwen/qwen-2-vl-72b-instruct`, `openrouter/google/gemini-flash-1.5`) **or a locally served small VLM** (e.g. `ollama/llama3.2-vision`, `ollama/qwen2.5-vl`, or a vLLM endpoint) by changing one `model` string.
- **`instructor`** — wraps the LLM call to return a **Pydantic-validated** object, mapping directly onto our `BiosState` schema. It handles corrective retries on malformed JSON, replacing the hand-rolled 3-attempt retry loop in `vlm_client.py`.

Provider is selected by env:

```
VLM_PROVIDER=openrouter | ollama | mock
VLM_MODEL=openrouter/qwen/qwen-2-vl-72b-instruct   # or ollama/llama3.2-vision
OPENROUTER_API_KEY=<doppler-injected, OpenRouter only>
VLM_BASE_URL=http://localhost:11434   # Ollama/vLLM local serving
```

`mock` remains the default for tests and offline development.

### 3.2 Tool signature

```python
@mcp.tool(name="kvm_vlm_parse", annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True})
async def kvm_vlm_parse(screenshot_ref: str, previous_state_id: str | None = None, last_action: str | None = None) -> dict:
    """
    Parse a BIOS screenshot with the configured VLM (OpenRouter or local) and return
    a schema-validated structured description (screen title, breadcrumbs, controls,
    values, options, blocklist flags). All transactions are logged to the trace ledger.
    """
```

`screenshot_ref` is a screenshot cache id/path (not raw bytes over stdio). The sidecar reads the frame from the capture cache, so payloads stay small and every parse is tied to a persisted frame for auditing.

---

## 4. Runtime Perception Pipeline (match-first)

`bios_observe_state` and navigation hops follow a **local-match-first** pipeline to avoid VLM cost/latency on known screens:

```
capture screenshot
  → compute phash + local OCR fingerprint
  → kvm_match_screen against known graph nodes
      ├─ match (high confidence): hydrate BiosState from stored node → DONE (no VLM)
      └─ no match / low confidence / drift: kvm_vlm_parse → normalize → persist node
  → update position tracker
  → append to trace
```

The VLM is invoked on: unknown screens during crawl, drift during navigation, dropdown/option parsing during mutation, and before/after value verification during save.

---

## 5. Implementation Steps

- **Phase 1: Docs (this PR).** Rewrite plan/decisions/architecture/skill to the 3-tier surface + framework choice.
- **Phase 2: Bug fixes.** Fix the `asyncio.to_thread` wrapping of the async `parse_screenshot` in `observe.py`.
- **Phase 3: VLM framework.** Add `instructor` + `litellm` deps; rewrite `vlm_client.py` to use them with provider routing; keep `mock`.
- **Phase 4: Tool implementation.** Add `kvm_vlm_parse`, `kvm_match_screen`, `bios_save_and_reboot`; migrate raw `kvm_*` → `comet_raw_*` aliases; reposition `bios_grant_human_approval` as out-of-band.
- **Phase 5: Tests.** VLM contract tests (mock), match-first bypass tests, save-and-reboot gating tests.
- **Phase 6: Live drive.** Smoke-test against the Comet at `192.168.0.126` (connect, screenshot, sysinfo). BIOS not available yet — refine live.
