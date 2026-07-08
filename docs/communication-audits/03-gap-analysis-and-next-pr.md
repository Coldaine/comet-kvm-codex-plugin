# Gap Analysis and Recommended Next PR

## Gap Table

| Gap | Existing Evidence | Needed Change | Confidence |
|---|---|---|---|
| `SKILL.md` is not yet an action-time router. | Current rules are compact and route to references: `skills/comet-bios-triage/SKILL.md:10-28`. | Add a lazy-loaded workflow/router reference or expand a dedicated reference doc with exact action gates. | Medium-high |
| Cartographer runtime is missing. | Architecture describes crawl flow: `docs/architecture.md:263-272`; no tool exists in `glkvm_mcp.py`. | Implement offline-first cartographer skeleton after eval foundation. | High |
| State engine is missing. | Planned in `docs/decisions.md:34-36`; no code exists. | Add state engine only after map/trace fixtures exist. | High |
| `observe_state`, `kvm_current_screen`, `kvm_in_sync` are missing. | Mentioned as planned read-only tools: `docs/decisions.md:34-36`; current tools are in `glkvm_mcp.py:293-884`. | Add read-only state tools when state engine exists. | High |
| Raw HID tools are not policy-gated. | Tools directly send keys/mouse: `glkvm_mcp.py:400-580`; only annotations mark destructive status. | Add policy layer before mutation-level BIOS tools. | High |
| `Enter` is not context-gated. | Architecture says VLM flags blocklists before Enter: `docs/architecture.md:191-212`; current `kvm_send_keys` sends directly: `glkvm_mcp.py:436-475`. | Add state-aware or mode-aware gate before BIOS automation uses Enter. | High |
| Safety policy is distributed across docs. | `skills/comet-bios-triage/SKILL.md:20-28`, `skills/comet-bios-triage/references/stateful-control-model.md:57-74`, `docs/architecture.md:191-212`. | Add a centralized action matrix and eventually executable policy tests. | High |
| VLM prompt is prose-only, not machine-validated. | Schema is in Markdown: `docs/vlm-prompt-contract.md:42-76`. | Add JSON Schema or Pydantic model plus fixture validation. | High |
| VLM client is missing. | Prompt contract says future code artifact: `docs/vlm-prompt-contract.md:4-10`. | Add after schema/eval foundation. | High |
| Graph/index persistence is missing. | Intended by `docs/decisions.md:47-54`, `docs/architecture.md:249-262`. | Add fixture format before live map store. | High |
| Run ledger lacks per-action evidence recording. | Required fields are documented: `skills/comet-bios-triage/references/stateful-control-model.md:44-55`; ledger only create/phase: `scripts/run_ledger.py:44-82`. | Extend ledger tests first, then add action records. | High |
| Smoke tests omit OCR tools. | `tests/test_smoke.py:24-38`; OCR tools exist at `glkvm_mcp.py:751-873`. | Add OCR tools to expected set. | High |
| Golden screenshot/eval fixtures are missing. | `.gitignore` ignores images: `.gitignore:30-36`; no fixture tree exists. | Add synthetic/redacted fixture policy and JSON fixtures first. | High |
| `state/` ignore is too narrow. | `.gitignore` ignores `state/*.json` only: `.gitignore:26`. | Ignore `state/*` with `.gitkeep` exception. | Medium |

## Smallest Safe Next PR

The safest next PR should be **offline-only**. It should not connect to a Comet, send HID input, invoke a VLM API, or add mutation tools.

### Proposed PR Title

`Add offline eval foundation for BIOS sidecar contracts`

### Proposed Files to Change

| File | Change |
|---|---|
| `tests/test_smoke.py` | Include `kvm_ocr_screenshot` and `kvm_ocr_click` in expected tool coverage. Optionally assert the documented 15-tool count. |
| `tests/test_run_ledger.py` | New tempdir-based tests for `create_run`, `set_phase`, invalid run id, invalid phase, duplicate run. |
| `tests/test_comet_preflight.py` | New tests for Tesseract discovery logic and CLI exit behavior using mocks/env isolation. |
| `tests/fixtures/vlm/` | New synthetic or redacted expected JSON fixtures based on `docs/vlm-prompt-contract.md`. Start JSON-only if image policy is not settled. |
| `tests/test_vlm_contract.py` | Validate fixture JSON against schema/model. |
| `.gitignore` | Tighten `state/*` ignores and add narrow fixture exceptions if image fixtures are introduced. |
| `docs/communication-audits/` | Keep this audit pack as context for why the PR is scoped offline-first. |

### Explicit Non-Goals for Next PR

- No live Comet/KVM calls.
- No `apply_setting` tool.
- No raw HID policy bypass changes.
- No real screenshots, HWiNFO logs, credentials, or runtime state.
- No state-engine implementation yet.
- No hosted VLM API integration yet.

## Open Experiments

| Experiment | Why It Matters | Evidence |
|---|---|---|
| Verify `/userdata/media` writability on Comet. | Decides map storage location. | `docs/decisions.md:18-24`. |
| Test auth expiry and dropped WebSocket behavior. | Current code lacks refresh/re-login. | `glkvm_mcp.py:293-396`. |
| Confirm no-signal/black-screen response shape. | Needed for capture verification and safe controller logic. | Screenshot endpoint is implemented at `glkvm_mcp.py:584-636`, but failure modes are undocumented. |
| Choose VLM runtime. | Required before code-level VLM prompt integration. | `docs/vlm-prompt-contract.md:128-135`. |
| Compare screenshot-only vs screenshot-plus-OCR prompt inputs. | Determines perception pipeline. | OCR exists at `glkvm_mcp.py:650-873`; OCR hint is open at `docs/vlm-prompt-contract.md:128-135`. |
| Validate MSI Click BIOS screen taxonomy on real screenshots. | Current MSI assumptions are workflow-level, not parser-level. | `skills/comet-bios-triage/references/msi-z690-bios-workflow.md:1-37`. |
