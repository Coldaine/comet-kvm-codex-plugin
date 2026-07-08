# Plan: Repivot to KVM Core as Product

> **Branch:** `refactor/kvm-core-extraction` from `feat/remediation-vlm-wiring`
> **Pre-condition:** clean working tree

## Architecture

Two stacked products, one MCP server:

```
glkvm_mcp.py (entry point)
 ├── KVM Core (kvm_core/)   — universal physical-machine control
 └── BIOS Sidecar (bios_sidecar/) — optional BIOS-aware orchestration
```

The KVM core owns transport (CometClient, capture, HID, OCR). The BIOS sidecar imports from the KVM core — not the other way around.

## Decisions

| # | Decision | Resolved |
|---|----------|----------|
| D1 | Transport layer (`comet/`) moves to `kvm_core/` | Yes — git mv, verbatim |
| D2 | OCR moves to `kvm_core/` | Yes — git mv, verbatim |
| D3 | `bios_sidecar/policy/` deleted entirely | Yes — engine, approvals, hazards, matrix.yaml |
| D4 | `comet_raw_*` alias tools deleted | Yes — 10 duplicates of kvm_* tools |
| D5 | `bios_connect` / `bios_disconnect` deleted | Yes — kvm_connect is the session lifecycle |
| D6 | `bios_grant_human_approval` deleted | Yes — no approval layer |
| D7 | `approval_id` / `plan_id` params removed | Yes — from mutate tools and runtime |
| D8 | `PolicyProfile` enum deleted | Yes — only existed for approval gating |
| D9 | `bios://policy/current` resource deleted | Yes — calls deleted policy_engine |
| D10 | State machine (`_TRANSITION_MATRIX`, `_guard_transition`, `RuntimeState`) **stays** | Yes — runtime safety, not policy |
| D11 | `AWAITING_APPROVAL` removed from `RuntimeState` | Yes — only approval-specific value |
| D12 | `bios_crawl_step` / `bios_crawl_region` `policy_profile` param removed | Yes — meaningless without PolicyEngine |
| D13 | Visual verification in `bios_save_and_reboot` **stays** | Yes — screen-state verification, not approval |
| D14 | Tool annotations **stay** | Yes — metadata, not policy |
| D15 | VLM stays in `bios_sidecar/perception/` | Yes — sidecar-internal perception tool |
| D16 | `crawl.py` blocklist_flag guard removed | Yes — driver handles hazards |

## Target file tree

```
src/
├── kvm_core/                      # KVM Core — the base product
│   ├── __init__.py
│   ├── server.py                  # FastMCP("comet-kvm") instance
│   ├── runtime.py                 # KVMRuntime: client + capture + OCR
│   ├── comet/                     # moved from bios_sidecar/comet/ (verbatim)
│   │   ├── __init__.py
│   │   ├── client.py
│   │   ├── capture.py
│   │   ├── hid.py
│   │   └── session.py
│   └── ocr.py                     # moved from bios_sidecar/perception/ocr.py
│
├── bios_sidecar/                  # Optional — imports from kvm_core
│   ├── mcp/server.py              # imports mcp from kvm_core; registers bios_* tools
│   ├── controller/                # observe, crawl, navigate, mutate, recover, settle
│   ├── state/                     # graph, matcher, store, hashing, capability_index
│   ├── perception/                # vlm_client, contract, models, normalize
│   ├── domain/                    # models, enums, schemas
│   ├── adapters/
│   └── trace/
│
├── [DELETED] bios_sidecar/policy/
└── glkvm_mcp.py                   # entry: imports mcp from kvm_core, registers kvm_* tools
```

## Implementation steps

### Phase 0: Branch + clean tree
1. `git checkout -b refactor/kvm-core-extraction`
2. Ensure clean working tree

### Phase 1: Create kvm_core package (additive)
3. `src/kvm_core/__init__.py` — empty
4. `src/kvm_core/server.py`:
   ```python
   from mcp.server.fastmcp import FastMCP
   mcp = FastMCP("comet-kvm")
   ```
5. `src/kvm_core/runtime.py` — KVMRuntime class + `get_kvm_runtime()` singleton. Imports from `src.kvm_core.comet.*` and `src.kvm_core.ocr` (dead code until Phase 2 — fine).
6. No existing imports change yet. Tests pass unchanged.

### Phase 2: git mv transport + OCR, fix all imports
7. `git mv src/bios_sidecar/comet/ src/kvm_core/comet/`
8. `git mv src/bios_sidecar/perception/ocr.py src/kvm_core/ocr.py`
9. Fix internal imports in moved files:
   - `kvm_core/comet/session.py:4` → `from src.kvm_core.comet.client`
   - `kvm_core/comet/hid.py:3` → same
   - `kvm_core/comet/capture.py:7` → same
10. Fix all external imports (13 files + 2 OCR files):
    - `controller/runtime.py`, `observe.py`, `mutate.py`, `navigate.py`, `crawl.py`, `recover.py`, `settle.py` — swap `bios_sidecar.comet.*` → `kvm_core.comet.*`
    - `controller/observe.py`, `runtime.py` — swap `bios_sidecar.perception.ocr` → `kvm_core.ocr`
    - `scripts/comet_smoke_test.py:32` — same
    - `tests/test_policy_engine.py` — skip (deleted in Phase 4)
11. Run `python -m pytest tests/ -x` — all pass

### Phase 3: Switch mcp instance + runtime ownership
12. `bios_sidecar/mcp/server.py`:
    - Replace `from mcp.server.fastmcp import FastMCP, Image` and `mcp = FastMCP("glkvm_sidecar")` with `from src.kvm_core.server import mcp`
    - Keep `from mcp.server.fastmcp import Image` if needed for `get_current_screen()` return type
13. `glkvm_mcp.py:28` — change to:
    ```python
    from src.kvm_core.server import mcp
    from src.kvm_core.runtime import get_kvm_runtime
    import src.bios_sidecar.mcp.server  # registers bios_* tools on mcp
    ```
14. `glkvm_mcp.py` — replace all `get_runtime()` calls in KVM tools with `get_kvm_runtime()`:
    - `_require_client()`, `kvm_status()`, `kvm_ocr_screenshot()`, `kvm_ocr_click()`, `_safe_screenshot_path()`
15. Refactor `StatefulBiosRuntime.__init__()` — delegate to KVMRuntime:
    - Remove direct `self.client`, `self.capture_mgr`, `self.ocr_mgr`
    - Add `self.kvm = get_kvm_runtime()` at init
    - `connect_comet()` → delegates to `self.kvm.connect()`, then sets up BIOS session state
    - `disconnect_comet()` → delegates to `self.kvm.disconnect()`
    - All controller access: `self.client` → `self.kvm.client`, `self.capture_mgr` → `self.kvm.capture_mgr`

### Phase 4: Delete policy layer + approval scaffolding
16. `git rm -r src/bios_sidecar/policy/`
17. `server.py` — delete `bios://policy/current` resource, delete `bios_grant_human_approval`, `bios_connect`, `bios_disconnect` tools
18. `server.py` — strip `plan_id`, `approval_id` from `bios_apply_setting_change`; strip `approval_id` from `bios_save_and_reboot`; strip `policy_profile` from `bios_crawl_step`, `bios_crawl_region`
19. `domain/enums.py` — delete `PolicyProfile` enum, delete `AWAITING_APPROVAL` from `RuntimeState`
20. `runtime.py` — remove policy imports (lines 16-17); remove `self.approval_tracker`, `self.policy_engine`; remove `AWAITING_APPROVAL` row from `_TRANSITION_MATRIX`; strip `policy_engine` from `BiosCrawler`/`BiosMutator` construction; strip `policy_profile`, `approval_id`, `plan_id` from method signatures
21. `crawl.py` — remove `PolicyEngine` import; remove `self.policy_engine`; remove all `self.policy_engine.evaluate()` calls — just send the key directly; remove `policy_profile` param from `execute_crawl_step`, `dfs_crawl`, `_heuristic_pick`, `_create_edge`; remove `policy_decision` hardcoded string from `_create_edge` `EdgeAction`; remove `blocklist_flag` early-return guard in `dfs_crawl` (driver handles hazards)
22. `mutate.py` — remove `PolicyEngine` import; remove `self.policy_engine`; `propose_setting_change()` — remove `approval_tracker.request_approval()` call, return plan without `approval_id`; `apply_setting_change()` — remove `approval_id` param and approval check, remove `policy_engine.evaluate` for Enter, just send Enter; `save_and_reboot()` — remove `approval_id` param and approval check, remove `policy_engine.evaluate` for F10, **keep visual verification** (lines 193-204)
23. `navigate.py` — strip `policy_profile` param from `navigate_to()` signature
24. `domain/enums.py` — remove orphaned `EventClass` values: `POLICY_DECIDED`, `APPROVAL_REQUESTED`, `APPROVAL_GRANTED`
25. `runtime.py` — update `trace.log_event()` calls: switch `APPROVAL_GRANTED` → `ACTION_EXECUTED` in `apply_setting_change` and `save_and_reboot`; drop `policy_decision` fields
26. Delete `tests/test_policy_engine.py`

Checkpoint: `python -m pytest tests/ -x` — remaining tests pass; `test_graph_transitions.py` needs no changes (only tests BiosGraph/StateSyncer, no policy/state-machine references)

### Phase 5: Delete comet_raw_* aliases
27. `glkvm_mcp.py` — delete all 10 `comet_raw_*` tool functions
28. `tests/test_smoke.py` — update `EXPECTED_TOOLS`: remove `comet_raw_send_keys`, `comet_raw_screenshot`; remove `bios_connect`, `bios_disconnect`, `bios_grant_human_approval`

Checkpoint: `python tests/test_smoke.py` passes

### Phase 6: Verify
29. `python -m pytest tests/ -x` — all pass
30. `python tests/test_smoke.py` — all pass
31. `uv run --script ./glkvm_mcp.py` — starts without import errors
32. Grep verification — zero matches for:
    - `bios_sidecar.policy`
    - `comet_raw_`
    - `approval_id\|plan_id\|grant_human_approval`
    - `PolicyProfile\|PolicyEngine\|ApprovalTracker`
    - `bios_sidecar\.comet`
    - `bios_sidecar\.perception\.ocr`

## What stays verbatim (git mv only)
- `comet/client.py`, `comet/capture.py`, `comet/hid.py`, `comet/session.py`, `ocr.py`
- `controller/observe.py`, `settle.py`, `recover.py`, `navigate.py` (import paths only)
- `state/*`, `perception/vlm_client.py`, `perception/contract.py`, `perception/normalize.py`
- `domain/models.py`, `adapters/*`, `trace/*`

## What stays in place (do NOT delete)
- `_TRANSITION_MATRIX`, `_guard_transition`, `RuntimeState` (minus `AWAITING_APPROVAL`), all `self.state` tracking
- Visual verification in `mutate.py:193-204`
- `readOnlyHint`/`destructiveHint`/`idempotentHint` annotations
- `_safe_screenshot_path` path validation
- Stale key watchdog + pinger in CometClient

## Risks
1. **Import breakage** — 13 files reference `bios_sidecar.comet.*`. Phase 2 checkpoint catches misses.
2. **Bios_* tools silently missing** — `import src.bios_sidecar.mcp.server` in glkvm_mcp.py is the side-effect that registers tools. If missing, bios_* tools won't appear. Phase 3 smoke test catches this.
3. **KVMRuntime delegation** — `self.client` → `self.kvm.client` throughout runtime.py + controllers. Mechanical, grep verifiable.
4. **No behavioral tests for KVM core** — smoke test checks registration only. A live-connection test is out of scope.
