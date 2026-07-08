# Current Implementation Inventory

## Authoritative Documents

| File | Status | Role | Evidence | Confidence |
|---|---|---|---|---|
| `docs/NORTH_STAR.md` | Existing | Highest authority for goals and scope. | Authority order: `docs/NORTH_STAR.md:24-34`; goals: `docs/NORTH_STAR.md:3-22`. | High |
| `docs/decisions.md` | Existing | Implementation decisions. | Authority statement: `docs/decisions.md:3-5`; D1-D9: `docs/decisions.md:6-54`. | High |
| `docs/architecture.md` | Existing | Full architecture and rationale. | Purpose: `docs/architecture.md:3-6`; layout/components: `docs/architecture.md:7-64`. | High |
| `docs/vlm-prompt-contract.md` | Existing draft | VLM prompt/schema design artifact. | Status and purpose: `docs/vlm-prompt-contract.md:1-16`. | High |
| `skills/comet-bios-triage/SKILL.md` | Existing | Driver-agent skill. | Trigger and rules: `skills/comet-bios-triage/SKILL.md:1-28`. | High |
| `AGENTS.md` | Existing | Developer-agent operating rules. | Role topology: `AGENTS.md:9-21`; operating rules: `AGENTS.md:23-30`. | High |

## North Star Requirements

| Requirement | Status | Evidence | Confidence |
|---|---|---|---|
| Package `kennypeh85/glkvm-mcp` fork as Comet KVM hardware-triage plugin. | Existing goal | `docs/NORTH_STAR.md:5`. | High |
| Not VM orchestration or generic remote desktop. | Existing anti-scope | `docs/NORTH_STAR.md:5`. | High |
| Codex first; cross-tool manifests deferred. | Existing goal | `docs/NORTH_STAR.md:7`. | High |
| BIOS cartography first spike. | Existing goal | `docs/NORTH_STAR.md:9-13`. | High |
| MSI Z690 one-setting-per-run workflow with HWiNFO validation. | Existing goal | `docs/NORTH_STAR.md:15-18`. | High |

## Architecture Commitments

| Component | Status | Evidence | Confidence |
|---|---|---|---|
| Thin-manifest shared-core layout. | Existing architecture | `docs/architecture.md:45-64`. | High |
| Single-file MCP server for current scope. | Existing implementation and design | `docs/architecture.md:65-140`, `glkvm_mcp.py:1-11`. | High |
| Three-agent topology. | Existing architecture | `docs/architecture.md:142-166`, `AGENTS.md:15-21`. | High |
| VLM as perception service, not navigator. | Existing design | `docs/architecture.md:168-190`, `docs/vlm-prompt-contract.md:23-30`. | High |
| Near-exhaustive crawl with blocklisted zones. | Intended design | `docs/architecture.md:191-212`. | High |
| Deterministic navigation plus VLM perception split. | Intended design | `docs/architecture.md:213-222`. | High |
| State engine via perceptual hash and OCR fingerprint. | Intended design | `docs/architecture.md:234-247`. | High |
| Semantic Capability Index plus screen graph. | Intended design | `docs/architecture.md:249-262`, `docs/decisions.md:47-54`. | High |

## Skill Boundary Inventory

The current skill is compact and mostly routes to supporting docs.

| Skill Element | Status | Evidence | Confidence |
|---|---|---|---|
| Activation surface covers Comet/GLKVM, BIOS, UEFI, MSI Z690, HWiNFO, undervolt testing. | Existing | `skills/comet-bios-triage/SKILL.md:1-4`. | High |
| Skill says use MCP tools as hands and eyes, not a blind macro engine. | Existing | `skills/comet-bios-triage/SKILL.md:6-8`. | High |
| Skill instructs driver to read architecture, VLM contract, state model, MSI workflow, HWiNFO loop. | Existing | `skills/comet-bios-triage/SKILL.md:10-16`. | High |
| Skill marks `bios-cartography.md` as superseded historical draft. | Existing | `skills/comet-bios-triage/SKILL.md:18`. | High |
| Skill rules require no blind key sequences, screenshots, one variable per run, visible confirmation, release-all recovery, abort conditions, and ledger use. | Existing | `skills/comet-bios-triage/SKILL.md:20-28`. | High |
| Action-time router shape is not fully encoded in `SKILL.md`. | Missing/partial | Skill has rules but no decision tree: `skills/comet-bios-triage/SKILL.md:20-28`. | Medium-high |

## MCP/API Implementation Inventory

### Server and Configuration

| Item | Status | Evidence | Confidence |
|---|---|---|---|
| MCP config exists as `comet-kvm`. | Existing | `.mcp.json:1-12`. | High |
| FastMCP server exists. | Existing | `glkvm_mcp.py:283`. | High |
| Server runs over stdio. | Existing | `glkvm_mcp.py:900-904`. | High |
| MCP resources and prompts are absent. | Missing | No `@mcp.resource` or `@mcp.prompt`; tools are defined with `@mcp.tool` at `glkvm_mcp.py:293-884`. | High |

### Authentication and Session

| Item | Status | Evidence | Confidence |
|---|---|---|---|
| Connection state is global singleton `_conn`. | Existing | `glkvm_mcp.py:157-174`. | High |
| Auth endpoint is `POST /api/auth/login`. | Existing | `glkvm_mcp.py:322-325`. | High |
| Login form uses `user`, `passwd`, `expire`. | Existing | `glkvm_mcp.py:322-325`. | High |
| Auth token comes from `auth_token` cookie. | Existing | `glkvm_mcp.py:327-331`. | High |
| Two-step login is not implemented. | Missing | `glkvm_mcp.py:327-328`. | High |
| Session refresh/re-login is not implemented. | Missing | Only `kvm_connect` and `kvm_disconnect` manage auth: `glkvm_mcp.py:293-396`. | High |

### Screenshot API

| Item | Status | Evidence | Confidence |
|---|---|---|---|
| Screenshot endpoint is `GET /api/streamer/snapshot`. | Existing | `glkvm_mcp.py:608`, `glkvm_mcp.py:632`, `glkvm_mcp.py:789`, `glkvm_mcp.py:821`. | High |
| Screenshot params include `allow_offline=true`. | Existing | `glkvm_mcp.py:603`, `glkvm_mcp.py:627`, `glkvm_mcp.py:784`, `glkvm_mcp.py:820`. | High |
| Preview params include `preview`, `preview_max_width`, `preview_quality`. | Existing | `glkvm_mcp.py:604-607`, `glkvm_mcp.py:628-631`. | High |
| `kvm_screenshot` returns MCP image content. | Existing | `glkvm_mcp.py:584-610`. | High |
| `kvm_screenshot_to_file` writes a file. | Existing side effect | `glkvm_mcp.py:613-636`. | High |

### HID API

| Item | Status | Evidence | Confidence |
|---|---|---|---|
| HID control WebSocket path is `/api/ws?auth_token=<token>&stream=false`. | Existing | `glkvm_mcp.py:338-350`. | High |
| Keyboard message shape is `event_type: key`, with `key`, `state`, `finish`. | Existing | `glkvm_mcp.py:215-221`. | High |
| Mouse button message shape is `event_type: mouse_button`. | Existing | `glkvm_mcp.py:228-235`. | High |
| Mouse move message shape is `event_type: mouse_move`, with normalized int16 coordinates. | Existing | `glkvm_mcp.py:238-246`. | High |
| Mouse wheel message shape is `event_type: mouse_wheel`. | Existing | `glkvm_mcp.py:249-256`. | High |
| WebSocket keepalive sends `b"\x00"`. | Existing | `glkvm_mcp.py:199-207`. | High |

### Current MCP Tools

| Tool | Status | Side Effect | Evidence |
|---|---|---|---|
| `kvm_connect` | Existing | Opens authenticated session. | `glkvm_mcp.py:293-358` |
| `kvm_disconnect` | Existing | Closes session and releases keys. | `glkvm_mcp.py:361-396` |
| `kvm_send_text` | Existing | Types text. | `glkvm_mcp.py:400-433` |
| `kvm_send_keys` | Existing | Sends key chord. | `glkvm_mcp.py:436-475` |
| `kvm_hold_key` | Existing | Holds key up to 5000 ms. | `glkvm_mcp.py:478-501` |
| `kvm_release_all` | Existing | Releases tracked keys. | `glkvm_mcp.py:504-516` |
| `kvm_mouse_move` | Existing | Moves mouse. | `glkvm_mcp.py:520-534` |
| `kvm_mouse_move_pct` | Existing | Moves mouse. | `glkvm_mcp.py:537-545` |
| `kvm_mouse_click` | Existing | Clicks mouse. | `glkvm_mcp.py:548-565` |
| `kvm_mouse_scroll` | Existing | Scrolls mouse. | `glkvm_mcp.py:568-580` |
| `kvm_screenshot` | Existing | Read-only capture. | `glkvm_mcp.py:584-610` |
| `kvm_screenshot_to_file` | Existing | Writes local file. | `glkvm_mcp.py:613-636` |
| `kvm_ocr_screenshot` | Existing | Read-only capture + OCR. | `glkvm_mcp.py:751-791` |
| `kvm_ocr_click` | Existing | OCR + mouse move + click. | `glkvm_mcp.py:794-873` |
| `kvm_status` | Existing | Read-only status. | `glkvm_mcp.py:884-894` |

## Safety and Policy Inventory

| Safety Layer | Status | Evidence | Confidence |
|---|---|---|---|
| MCP annotations mark destructive hints. | Existing metadata | Examples: `glkvm_mcp.py:400`, `glkvm_mcp.py:436`, `glkvm_mcp.py:548`, `glkvm_mcp.py:794`. | High |
| Runtime policy gate for raw key/mouse tools. | Missing | Tools send directly after `_require_conn`; no state/policy checks at `glkvm_mcp.py:400-580`. | High |
| Blocklist exists in architecture and VLM contract. | Intended/documented | `docs/architecture.md:191-212`, `docs/vlm-prompt-contract.md:61-65`. | High |
| Executable blocklist enforcement. | Missing | No cartographer/state engine exists to consume `blocklist_flag`. | High |
| Read-only live-safe MCP sequence. | Existing doc | `skills/comet-bios-triage/references/stateful-control-model.md:63-74`. | High |
| Action recording requirements. | Existing doc, missing implementation | `skills/comet-bios-triage/references/stateful-control-model.md:44-55`. | High |

## Perception Inventory

| Item | Status | Evidence | Confidence |
|---|---|---|---|
| Tesseract OCR implementation. | Existing | `glkvm_mcp.py:650-748`. | High |
| OCR screenshot tool. | Existing | `glkvm_mcp.py:751-791`. | High |
| OCR click tool. | Existing | `glkvm_mcp.py:794-873`. | High |
| VLM prompt schema. | Existing draft | `docs/vlm-prompt-contract.md:42-76`. | High |
| VLM invalid JSON retry behavior. | Existing draft | `docs/vlm-prompt-contract.md:118-126`. | High |
| VLM client/parser code. | Missing | Prompt contract says future code artifact: `docs/vlm-prompt-contract.md:4-10`. | High |

## Runtime, Graph, and Trace Inventory

| Item | Status | Evidence | Confidence |
|---|---|---|---|
| Run ledger create/update. | Existing | `scripts/run_ledger.py:44-82`. | High |
| Phase model. | Existing doc | `skills/comet-bios-triage/references/stateful-control-model.md:20-32`. | High |
| Screen-node state engine. | Intended/missing | `skills/comet-bios-triage/references/stateful-control-model.md:34-42`; no code. | High |
| Graph/index store. | Intended/missing | `docs/architecture.md:249-262`, `docs/decisions.md:47-54`; no code. | High |
| Replayable traces. | Missing | Action recording docs exist, but no trace files/scripts. | High |

## Tests and Evals Inventory

| Item | Status | Evidence | Confidence |
|---|---|---|---|
| CI smoke workflow. | Existing | `.github/workflows/ci.yml:1-36`. | High |
| Smoke test imports server and checks tool registration/signature. | Existing | `tests/test_smoke.py:1-84`. | High |
| OCR tools in smoke expected set. | Missing test coverage | `tests/test_smoke.py:24-38` omits `kvm_ocr_screenshot` and `kvm_ocr_click`; tools exist at `glkvm_mcp.py:751-873`. | High |
| Golden screenshots. | Missing | No fixture directory; `.gitignore` ignores images at `.gitignore:30-36`. | High |
| Expected VLM JSON fixtures. | Missing | VLM schema documented at `docs/vlm-prompt-contract.md:42-76`, but no fixtures. | High |
| Parser scoring. | Missing | No scorer/eval script exists. | High |
