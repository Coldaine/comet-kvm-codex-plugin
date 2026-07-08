# Executive Summary

## Short Answer

The previous broad answer should be treated as a **design summary**, not a repo-grounded implementation audit. The repo currently has a strong documented architecture and an implemented low-level MCP transport layer, but the BIOS sidecar runtime is only partially implemented.

The current repo has:

- A clear north star for a Comet KVM hardware-triage plugin, not a generic remote desktop tool: `docs/NORTH_STAR.md:5`.
- A documented first spike for BIOS cartography using near-exhaustive crawl, VLM perception, perceptual hashing, and blocklisted dangerous zones: `docs/NORTH_STAR.md:9-13`.
- A single-file MCP server with auth, screenshot, keyboard, mouse, OCR, and status tools implemented in source: `glkvm_mcp.py:283-904`.
- A compact driver skill for Comet BIOS triage: `skills/comet-bios-triage/SKILL.md:1-28`.
- Draft VLM prompt/schema contract documentation, but no VLM implementation: `docs/vlm-prompt-contract.md:1-16`.

The current repo does **not** yet have:

- A cartographer tool.
- A deterministic BIOS DFS runtime/controller.
- A state engine implementation.
- An `observe_state`, `crawl_one_step`, `navigate_to`, or `apply_setting` MCP tool.
- A centralized executable safety policy engine.
- Graph/map storage code.
- Golden screenshots, parser fixtures, parser scoring, or replayable traces.

## Current-State Inventory

### Authority Stack

Authority is explicit:

1. `docs/NORTH_STAR.md`
2. `docs/decisions.md`
3. `docs/architecture.md`
4. `docs/vlm-prompt-contract.md`
5. `skills/comet-bios-triage/SKILL.md`
6. `skills/comet-bios-triage/references/stateful-control-model.md`
7. `docs/reference/comet-hardware.md`
8. `docs/reference/comet-api.md`
9. `AGENTS.md`

Evidence: `docs/NORTH_STAR.md:24-34`.

### Existing Implementation

- MCP server exists as `glkvm_mcp.py` and is configured in `.mcp.json`: `.mcp.json:1-12`, `glkvm_mcp.py:283`, `glkvm_mcp.py:900-904`.
- Comet auth exists via `POST /api/auth/login`: `glkvm_mcp.py:322-325`.
- HID input exists via `WSS /api/ws?auth_token=<token>&stream=false`: `glkvm_mcp.py:338-350`.
- Screenshot capture exists via `GET /api/streamer/snapshot`: `glkvm_mcp.py:608`, `glkvm_mcp.py:632`, `glkvm_mcp.py:789`, `glkvm_mcp.py:821`.
- OCR exists through Tesseract: `glkvm_mcp.py:650-748`, with tools at `glkvm_mcp.py:751-873`.
- Run ledger exists: `scripts/run_ledger.py:44-82`.
- Local preflight exists and performs no live KVM action: `scripts/comet_preflight.py:29-48`.

### Intended Architecture Not Yet Implemented

- State engine as internal asyncio loop: `docs/decisions.md:34-36`.
- Read-only state tools such as `kvm_current_screen` and `kvm_in_sync`: `docs/decisions.md:34-36`.
- Semantic Capability Index and screen-node graph: `docs/decisions.md:47-54`, `docs/architecture.md:249-262`.
- Cartography runtime flow: `docs/architecture.md:263-272`.

## Missing Pieces

| Area | Status | Evidence |
|---|---|---|
| VLM client | Missing | Prompt is documented as future code artifact: `docs/vlm-prompt-contract.md:4-10`. |
| Cartographer driver | Missing | Architecture describes flow, but no corresponding MCP tool or Python module exists: `docs/architecture.md:263-272`. |
| State engine | Missing | Planned as future internal loop: `docs/decisions.md:34-36`. |
| Safety policy engine | Missing | Current safety exists as prose and MCP annotations, not executable policy: `skills/comet-bios-triage/SKILL.md:20-28`, `glkvm_mcp.py:400-568`. |
| Fixtures/evals | Missing | Only smoke tests exist: `tests/test_smoke.py:1-84`; no fixture directory is present. |
| Replayable traces | Missing | Action recording is required by docs, but no trace implementation exists: `skills/comet-bios-triage/references/stateful-control-model.md:44-55`. |

## Recommended Next PR

The smallest safe next PR is an **offline eval and safety-contract foundation**, not live cartography.

Recommended contents:

1. Expand `tests/test_smoke.py` to assert OCR tools are registered.
2. Add tests for `scripts/run_ledger.py` using temp directories.
3. Add tests for `scripts/comet_preflight.py` using mocked env/path checks.
4. Add `tests/fixtures/vlm/` with synthetic or redacted JSON-only fixtures first.
5. Add a JSON-schema or Pydantic validator for the VLM contract.
6. Tighten `.gitignore` for `state/*`, with explicit test-fixture exceptions if image fixtures are later added.
7. Add a safety action matrix doc or test fixture that maps action categories to allowed, blocked, or requires-human-confirmation.

Do **not** put live Comet screenshots, credentials, HWiNFO logs, or real runtime state into the repo.

## Open Experiments

- Verify whether `/userdata/media` is writable on the target Comet; current decision says it is architecturally suitable but unverified without credentials: `docs/decisions.md:18-24`.
- Determine which VLM stack to use: hosted API, vLLM, Ollama, llama.cpp, or another path: `docs/vlm-prompt-contract.md:128-135`.
- Determine whether OCR should be sent alongside screenshots as VLM hint: `docs/vlm-prompt-contract.md:128-135`.
- Measure screenshot resolution needed for reliable parse: `docs/vlm-prompt-contract.md:128-135`.
- Confirm live Comet behavior for auth expiry, dropped WebSocket, black screen/no signal, reboot, and reconnect.
