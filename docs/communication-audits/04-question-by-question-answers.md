# Question-by-Question Answers

Each answer includes direct answer, evidence, existing implementation, proposed change if needed, unknowns/experiments, and confidence.

## 1. What is the repo's stated north star for this Comet KVM plugin?

**Answer:** Convert the upstream `glkvm-mcp` fork into a packaged plugin for GL.iNet Comet KVM-driven hardware triage workflows: BIOS configuration, pre-OS operations, and Windows validation on physical machines.

**Evidence:** `docs/NORTH_STAR.md:5`.

**Existing implementation:** Repo has plugin manifest/MCP/skill structure and a working MCP server.

**Proposed change:** None for the statement itself.

**Unknowns:** Packaging distribution flow beyond Codex is outside the current scope.

**Confidence:** High.

## 2. What does the current architecture say the major components are?

**Answer:** Thin Codex manifest, `.mcp.json`, single-file MCP server, driver skill, scripts, authority docs, reference docs, extras, runtime dirs, and tests.

**Evidence:** `docs/architecture.md:7-43`.

**Existing implementation:** Those files/directories exist in the repo.

**Proposed change:** None for inventory; future component additions should follow the same authority structure.

**Unknowns:** Exact package install layout is not yet proven.

**Confidence:** High.

## 3. What does the current `comet-bios-triage` skill actually do?

**Answer:** It routes driver agents for Comet/GLKVM BIOS/pre-OS workflows, points them to current authority/reference docs, warns against using the superseded cartography draft, and lists core runtime safety rules.

**Evidence:** `skills/comet-bios-triage/SKILL.md:1-28`.

**Existing implementation:** Markdown skill only; no executable skill router.

**Proposed change:** Add a dedicated action-time router reference if workflows become longer.

**Unknowns:** How much of the router belongs in skill Markdown versus MCP/state-engine code is not fully settled.

**Confidence:** High.

## 4. What activation boundaries, authority gates, retention rules, assembly rules, and verification contracts exist in `SKILL.md`?

**Answer:** Activation boundaries exist in the frontmatter; authority assembly exists as a read-before-changing list; verification rules include screenshots before/after, visible old/new value confirmation, one variable per run, abort conditions, and ledger use. Explicit authority gates are not implemented in `SKILL.md`; the skill routes to authority docs but does not enforce a gate. Retention rules are not in `SKILL.md`; they live in decisions/docs.

**Evidence:** Activation: `skills/comet-bios-triage/SKILL.md:1-4`; assembly: `skills/comet-bios-triage/SKILL.md:10-18`; verification/safety: `skills/comet-bios-triage/SKILL.md:20-28`; retention: `docs/decisions.md:6-12`.

**Existing implementation:** Skill prose plus run ledger script.

**Proposed change:** Add explicit action-time gate table and escalation rules.

**Unknowns:** Human approval UX for mutation is not defined.

**Confidence:** High.

## 5. What is missing from `SKILL.md` relative to a sidecar BIOS workflow?

**Answer:** It lacks a concrete decision tree for map availability, read-only crawl, state drift, blocklist detection, save confirmation, human approval, and mutation refusal.

**Evidence:** Current skill is only 28 lines: `skills/comet-bios-triage/SKILL.md:1-28`; intended flow is in `docs/architecture.md:263-282` and `skills/comet-bios-triage/references/stateful-control-model.md:57-74`.

**Existing implementation:** Partial workflow references.

**Proposed change:** Add a lazy-loaded `references/action-time-router.md` or similar.

**Unknowns:** Whether the router should be primarily docs or generated from executable policy.

**Confidence:** Medium-high.

## 6. Does the repo already implement a Comet/GLKVM API client?

**Answer:** Yes, but not as a separate client module. It is embedded in `glkvm_mcp.py` through a global `Connection` containing `httpx.AsyncClient` and a WebSocket.

**Evidence:** `glkvm_mcp.py:157-174`, `glkvm_mcp.py:319-355`.

**Existing implementation:** Embedded singleton client.

**Proposed change:** Consider extracting client/session abstraction only if state engine/controller complexity requires it.

**Unknowns:** Multi-device/multi-session requirements are not established.

**Confidence:** High.

## 7. What exact endpoint/path is used for screenshots?

**Answer:** `GET /api/streamer/snapshot` with `allow_offline=true` and optional preview params.

**Evidence:** `glkvm_mcp.py:603-608`, `glkvm_mcp.py:627-632`, `glkvm_mcp.py:784-789`, `glkvm_mcp.py:820-821`.

**Existing implementation:** `kvm_screenshot`, `kvm_screenshot_to_file`, `kvm_ocr_screenshot`, and `kvm_ocr_click` all use it.

**Proposed change:** Document/handle failure modes such as no signal or black frame.

**Unknowns:** Exact Comet error response for no signal/offline capture.

**Confidence:** High.

## 8. What exact endpoint/path/message shape is used for keyboard/HID injection?

**Answer:** WebSocket `WSS /api/ws?auth_token=<token>&stream=false`. Keyboard JSON is `{"event_type":"key","event":{"key":...,"state":...,"finish":...}}`.

**Evidence:** WebSocket URL: `glkvm_mcp.py:338-350`; key payload: `glkvm_mcp.py:215-221`; mouse payloads: `glkvm_mcp.py:228-256`.

**Existing implementation:** Raw keyboard and mouse tools.

**Proposed change:** Add policy/state gate before BIOS-level automation uses raw HID.

**Unknowns:** Live failure behavior on dropped WS/reboot.

**Confidence:** High.

## 9. How is Comet authentication/session handling implemented?

**Answer:** `kvm_connect` posts form data to `/api/auth/login`, expects `auth_token` cookie, then opens WebSocket with token as query parameter.

**Evidence:** `glkvm_mcp.py:322-339`.

**Existing implementation:** Auth and session open/close.

**Proposed change:** Add refresh/reconnect behavior later.

**Unknowns:** Token expiry duration and refresh options.

**Confidence:** High.

## 10. Is session refresh/re-login handled?

**Answer:** No.

**Evidence:** Auth lifecycle exists only in `kvm_connect` and `kvm_disconnect`: `glkvm_mcp.py:293-396`. Repo inventory during this audit found no refresh/re-login symbols or functions.

**Existing implementation:** None.

**Proposed change:** Add reconnect/refresh strategy once live failure modes are measured.

**Unknowns:** Firmware session expiry semantics.

**Confidence:** High.

## 11. Does an MCP server already exist?

**Answer:** Yes.

**Evidence:** `mcp = FastMCP("glkvm")` at `glkvm_mcp.py:283`; stdio entrypoint at `glkvm_mcp.py:900-904`; `.mcp.json:1-12`.

**Existing implementation:** Single-file FastMCP server.

**Proposed change:** None for existence.

**Unknowns:** Future module split timing.

**Confidence:** High.

## 12. What MCP tools/resources are currently exposed?

**Answer:** Fifteen tools: connect, disconnect, send text, send keys, hold key, release all, mouse move, mouse move pct, mouse click, mouse scroll, screenshot, screenshot to file, OCR screenshot, OCR click, status. No MCP resources are exposed.

**Evidence:** Tool decorators: `glkvm_mcp.py:293`, `361`, `400`, `436`, `478`, `504`, `520`, `537`, `548`, `568`, `584`, `613`, `751`, `794`, `884`.

**Existing implementation:** Tools only.

**Proposed change:** Consider MCP resources for screenshots/traces after trace storage exists.

**Unknowns:** Resource shape not designed.

**Confidence:** High.

## 13. Are any tools capable of sending raw keyboard input?

**Answer:** Yes: `kvm_send_text`, `kvm_send_keys`, `kvm_hold_key`, and recovery `kvm_release_all`.

**Evidence:** `glkvm_mcp.py:400-516`.

**Existing implementation:** Raw keyboard input tools exist.

**Proposed change:** Add context/policy gating for BIOS automation.

**Unknowns:** Whether raw tools should remain exposed for manual use while higher-level tools are gated.

**Confidence:** High.

## 14. If raw keyboard tools exist, are they policy-gated?

**Answer:** No. They carry MCP `destructiveHint` metadata, but there is no executable policy gate.

**Evidence:** Annotations at `glkvm_mcp.py:400`, `436`, `478`, `504`; direct send logic at `glkvm_mcp.py:419-475`.

**Existing implementation:** Metadata only.

**Proposed change:** Add policy layer for BIOS automation and/or mode-specific tool wrappers.

**Unknowns:** Exact bypass/admin mode requirements.

**Confidence:** High.

## 15. Is there an `observe_state` or equivalent perception tool?

**Answer:** Not at BIOS-state level. Existing perception is `kvm_screenshot` and `kvm_ocr_screenshot`; no semantic BIOS state parser exists.

**Evidence:** Screenshot/OCR tools at `glkvm_mcp.py:584-636`, `glkvm_mcp.py:751-791`; planned state tools at `docs/decisions.md:34-36`.

**Existing implementation:** Screenshot/OCR only.

**Proposed change:** Add read-only `observe_state` after schema/evals exist.

**Unknowns:** Exact response schema for state engine.

**Confidence:** High.

## 16. Is there a `crawl_one_step`, `navigate_to`, or `apply_setting` tool?

**Answer:** No.

**Evidence:** Current tool list in `glkvm_mcp.py:293-884`; repo inventory during this audit found no `crawl_one_step`, `navigate_to`, or `apply_setting` symbols.

**Existing implementation:** Missing.

**Proposed change:** Start with read-only `crawl_one_step` or offline simulator before `apply_setting`.

**Unknowns:** Human approval and safety gate design.

**Confidence:** High.

## 17. Which of those are existing vs proposed?

**Answer:** Existing: low-level screenshot/OCR/HID/status tools. Proposed/intended: state tools, cartography tools, graph/index tools. Missing and not yet safe: mutation-level `apply_setting`.

**Evidence:** Existing tools at `glkvm_mcp.py:293-884`; proposed state tools at `docs/decisions.md:34-36`; cartography flow at `docs/architecture.md:263-272`.

**Existing implementation:** Low-level tools.

**Proposed change:** Add read-only/introspection tools before mutation tools.

**Unknowns:** Naming and interface.

**Confidence:** High.

## 18. What runtime/controller code exists outside MCP?

**Answer:** Local helper scripts exist for preflight and run ledger. No BIOS controller runtime exists outside MCP.

**Evidence:** `scripts/comet_preflight.py:29-48`, `scripts/run_ledger.py:44-82`.

**Existing implementation:** Utility scripts only.

**Proposed change:** Add offline controller/eval scaffolding before live runtime.

**Unknowns:** Whether controller should be separate CLI/module or inside MCP server.

**Confidence:** High.

## 19. Who owns key timing, settle detection, retry, and capture verification?

**Answer:** Key timing is owned by `glkvm_mcp.py`. Settle detection, retry after bad capture, and capture verification are intended runtime/controller concerns but not implemented.

**Evidence:** Timing: `glkvm_mcp.py:52-57`, `262-277`; state engine/crawl flow intended: `docs/architecture.md:263-282`.

**Existing implementation:** Key timing and key watchdog only.

**Proposed change:** Add deterministic settle/capture verification in controller/state engine.

**Unknowns:** Settling thresholds and screenshot failure signatures.

**Confidence:** High.

## 20. Does a deterministic safety policy engine exist?

**Answer:** No.

**Evidence:** Safety is prose in `skills/comet-bios-triage/SKILL.md:20-28`, architecture blocklist in `docs/architecture.md:191-212`, and annotations in `glkvm_mcp.py:400-568`; no policy engine code exists.

**Existing implementation:** Prose + metadata.

**Proposed change:** Add policy matrix and executable checks.

**Unknowns:** Approval flow and bypass mechanics.

**Confidence:** High.

## 21. What actions are blocked in read-only mode?

**Answer:** No executable read-only mode exists. The documented live-safe sequence intentionally avoids target-changing input except `kvm_release_all` recovery.

**Evidence:** `skills/comet-bios-triage/references/stateful-control-model.md:63-74`.

**Existing implementation:** None as a mode.

**Proposed change:** Define read-only mode and enforce allowed actions in code.

**Unknowns:** Whether `Esc`, arrows, and `Enter` are allowed during cartography depends on state classification.

**Confidence:** High.

## 22. Is `Enter` context-gated based on current state?

**Answer:** No.

**Evidence:** `kvm_send_keys` sends requested combo directly: `glkvm_mcp.py:436-475`; architecture says blocklist flag should be checked before Enter in crawler: `docs/architecture.md:191-212`.

**Existing implementation:** Missing.

**Proposed change:** Gate Enter in cartographer/controller using VLM `blocklist_flag` and state classification.

**Unknowns:** Which state classes permit Enter safely.

**Confidence:** High.

## 23. Are F10, F6, M-FLASH, Secure Erase, password screens, and save/reset flows blocked?

**Answer:** Not in code. Flash, Secure Erase, RAID, Boot Order, and Password are blocklisted in design docs and VLM contract. F10/F6 and save/reset flows are not executable-policy blocked today.

**Evidence:** Blocklist: `docs/architecture.md:199-211`, `docs/vlm-prompt-contract.md:61-65`; raw key send lacks policy: `glkvm_mcp.py:436-475`.

**Existing implementation:** Missing executable block.

**Proposed change:** Add policy action matrix including F10/F6/save/defaults/reset.

**Unknowns:** Exact MSI BIOS key semantics for F6/defaults and save flows.

**Confidence:** High.

## 24. How are policy decisions logged?

**Answer:** They are not logged because no policy engine exists. Generic logging exists for connection/watchdog/release failures.

**Evidence:** Logger setup: `glkvm_mcp.py:60-61`; connection log: `glkvm_mcp.py:357`; watchdog logs: `glkvm_mcp.py:188-193`; action recording requirement: `skills/comet-bios-triage/references/stateful-control-model.md:44-55`.

**Existing implementation:** Generic logs only.

**Proposed change:** Add structured policy/audit log with action decisions.

**Unknowns:** Log destination and retention.

**Confidence:** High.

## 25. What BIOS state schema currently exists?

**Answer:** A draft VLM screen parse schema exists in Markdown; graph/index schema exists conceptually. No machine-validated BIOS state schema exists.

**Evidence:** VLM schema: `docs/vlm-prompt-contract.md:42-76`; graph/index: `docs/decisions.md:47-54`.

**Existing implementation:** Prose only.

**Proposed change:** Add JSON Schema/Pydantic model.

**Unknowns:** Final graph node/edge schema.

**Confidence:** High.

## 26. Is the schema machine-validated?

**Answer:** No.

**Evidence:** Schema is Markdown at `docs/vlm-prompt-contract.md:42-76`. Repo inventory during this audit found no schema or fixture files under `tests/`.

**Existing implementation:** Missing.

**Proposed change:** Add validator tests and fixtures.

**Unknowns:** Schema language choice.

**Confidence:** High.

## 27. What fields are mandatory in the VLM prompt contract?

**Answer:** The prompt lists `screen_title`, `menu_path`, `cursor_at`, `entries` with `label`, `type`, `value`, `options`, `key_to_enter`, plus `blocklist_flag` and `blocklist_keywords`. It does not formalize required-vs-nullable in machine schema.

**Evidence:** `docs/vlm-prompt-contract.md:47-63`.

**Existing implementation:** Draft prompt schema.

**Proposed change:** Convert to JSON Schema with required fields.

**Unknowns:** Whether nullable fields are required keys or optional keys.

**Confidence:** High.

## 28. Does the perception stack use OCR, VLM, or both?

**Answer:** Current implementation uses OCR only. Intended architecture uses VLM for crawl perception and OCR/perceptual hash for state matching; whether to pass OCR hints to VLM is open.

**Evidence:** OCR implementation: `glkvm_mcp.py:650-873`; VLM intended: `docs/architecture.md:168-190`; OCR hint open question: `docs/vlm-prompt-contract.md:128-135`.

**Existing implementation:** OCR only.

**Proposed change:** Add VLM client after schema/evals.

**Unknowns:** OCR+VLM fusion design.

**Confidence:** High.

## 29. What happens when VLM output is invalid JSON?

**Answer:** The draft contract says retry once with corrective prompt, retry once fresh, then log the screen as unparseable and continue crawl. No code implements this yet.

**Evidence:** `docs/vlm-prompt-contract.md:118-126`.

**Existing implementation:** Missing.

**Proposed change:** Implement exactly this behavior in VLM parser/controller.

**Unknowns:** Where unparseable screenshots are stored and TTL cleanup.

**Confidence:** High.

## 30. How is selected-control detection represented?

**Answer:** In the VLM prompt schema as `cursor_at`, the 0-indexed highlighted row position.

**Evidence:** `docs/vlm-prompt-contract.md:49-52`, justification at `docs/vlm-prompt-contract.md:84`.

**Existing implementation:** Prose schema only.

**Proposed change:** Add fixture examples with selected row validation.

**Unknowns:** How to handle BIOSes without visible highlight or with grid layouts.

**Confidence:** High.

## 31. How is modal/dropdown detection represented?

**Answer:** Dropdown-like settings are represented as `leaf-enum` with `options`. Modal state is not explicitly represented as its own top-level state class in the current VLM schema.

**Evidence:** `docs/vlm-prompt-contract.md:55-58`, type definitions at `docs/vlm-prompt-contract.md:67-73`.

**Existing implementation:** Partial in prose schema.

**Proposed change:** Add explicit modal/dialog/dropdown-open fields if fixtures show need.

**Unknowns:** How MSI Click BIOS exposes modals/dropdowns visually.

**Confidence:** Medium-high.

## 32. How are screenshot hash, perceptual hash, OCR hash, and semantic state hash handled?

**Answer:** They are intended but not implemented. Architecture says state engine uses perceptual hashing and OCR text fingerprinting; North Star mentions perceptual-hash cycle detection.

**Evidence:** `docs/NORTH_STAR.md:11`, `docs/architecture.md:236-240`, `docs/architecture.md:258-261`.

**Existing implementation:** Missing.

**Proposed change:** Add offline hashing fixtures and tests before live state engine.

**Unknowns:** Exact hash algorithms and merge thresholds.

**Confidence:** High.

## 33. Does a graph/state store exist?

**Answer:** No.

**Evidence:** Graph/index are described conceptually at `docs/decisions.md:47-54`; repo inventory during this audit found no graph/state store code or fixture files.

**Existing implementation:** Missing.

**Proposed change:** Add fixture format, then storage module.

**Unknowns:** On-Comet vs host data dir depends on storage experiment.

**Confidence:** High.

## 34. How are nodes and edges represented?

**Answer:** Conceptually: screen nodes keyed by perceptual hash + OCR fingerprint, edges labeled by transition keystroke. Not implemented.

**Evidence:** `docs/architecture.md:258-261`, `docs/decisions.md:47-54`.

**Existing implementation:** Missing.

**Proposed change:** Define graph JSON schema and fixtures.

**Unknowns:** Node identity fields, edge metadata, confidence fields.

**Confidence:** High.

## 35. How are loops, no-op transitions, and near-duplicate screens detected?

**Answer:** Cycle detection via perceptual hashing is intended; no-op and near-duplicate logic are not specified in implementation. Near-identical screens are an open design gap.

**Evidence:** `docs/NORTH_STAR.md:11`; state matching intent at `docs/architecture.md:236-240`.

**Existing implementation:** Missing.

**Proposed change:** Define and test screen identity/merge rules using synthetic traces.

**Unknowns:** Thresholds for temperature/clock-changing BIOS screens.

**Confidence:** Medium-high.

## 36. Does the repo include MSI Z690 / Click BIOS assumptions?

**Answer:** Yes, workflow-level MSI Z690 assumptions exist.

**Evidence:** Skill triggers include MSI Z690: `skills/comet-bios-triage/SKILL.md:1-4`; workflow settings at `skills/comet-bios-triage/references/msi-z690-bios-workflow.md:1-37`.

**Existing implementation:** Documentation only.

**Proposed change:** Add vendor adapter/schema after real fixtures.

**Unknowns:** Exact MSI Click BIOS screen/module taxonomy.

**Confidence:** High.

## 37. Which MSI-specific concepts are encoded, if any?

**Answer:** CPU Cooler Tuning, PL1, PL2, ICCMAX, CPU Lite Load Control, CPU Lite Load mode, LLC mode, CEP state, first safe run values, and Lite Load sweep order.

**Evidence:** `skills/comet-bios-triage/references/msi-z690-bios-workflow.md:3-29`.

**Existing implementation:** Documentation only.

**Proposed change:** Convert to fixture-backed workflow after map/index exists.

**Unknowns:** BIOS menu paths and exact labels for target board/BIOS version.

**Confidence:** High.

## 38. What vendor-adapter interface exists or should exist?

**Answer:** No vendor-adapter interface exists. It should be proposed only after graph/index fixtures establish what must vary by vendor/board.

**Evidence:** No code beyond generic MCP tools; MSI docs are prose at `skills/comet-bios-triage/references/msi-z690-bios-workflow.md:1-37`.

**Existing implementation:** Missing.

**Proposed change:** Later: board profile or adapter that maps setting aliases to graph/index labels.

**Unknowns:** Adapter boundaries and storage format.

**Confidence:** Medium-high.

## 39. Does an eval/golden screenshot set exist?

**Answer:** No.

**Evidence:** Repo inventory during this audit found no fixture tree; `.gitignore` ignores images at `.gitignore:30-36`.

**Existing implementation:** Missing.

**Proposed change:** Start with synthetic/redacted fixtures and JSON expected outputs.

**Unknowns:** Whether real screenshots can be sanitized safely.

**Confidence:** High.

## 40. Are parser outputs scored against expected JSON?

**Answer:** No.

**Evidence:** Repo inventory during this audit found no parser scoring script; only smoke test is `tests/test_smoke.py:1-84`.

**Existing implementation:** Missing.

**Proposed change:** Add offline scorer for JSON validity, labels, selected row, blocklist, and type classification.

**Unknowns:** Scoring weights.

**Confidence:** High.

## 41. Are traces replayable?

**Answer:** No.

**Evidence:** Action recording is documented at `skills/comet-bios-triage/references/stateful-control-model.md:44-55`; repo inventory during this audit found no trace replay files/scripts.

**Existing implementation:** Missing.

**Proposed change:** Add synthetic trace fixture and replay validator.

**Unknowns:** Trace format.

**Confidence:** High.

## 42. Can failed runs be promoted into fixtures?

**Answer:** No workflow exists for that. Runtime run ledger exists, and runtime dirs are ignored.

**Evidence:** Run ledger writes under `runs`: `scripts/run_ledger.py:44-82`; ignore rule: `.gitignore:27-28`; action evidence expectations: `skills/comet-bios-triage/references/stateful-control-model.md:44-55`.

**Existing implementation:** Missing.

**Proposed change:** Add manual redaction/promotion checklist before automation.

**Unknowns:** Data sensitivity policy for screenshots/logs.

**Confidence:** High.

## 43. What is the minimal safe v1 milestone?

**Answer:** Offline eval/contract foundation plus existing low-level MCP smoke coverage. Do not add mutation-level BIOS automation yet.

**Evidence:** Current implementation has low-level tools (`glkvm_mcp.py:293-884`) and smoke tests (`tests/test_smoke.py:1-84`), while state/cartography are intended but missing (`docs/architecture.md:263-282`).

**Existing implementation:** Low-level MCP only.

**Proposed change:** Add fixture/schema/tests and safety matrix.

**Unknowns:** Live Comet failure modes.

**Confidence:** High.

## 44. What files should be changed in the next PR?

**Answer:** `tests/test_smoke.py`, new tests for `scripts/run_ledger.py` and `scripts/comet_preflight.py`, new `tests/fixtures/vlm/` JSON fixtures, a schema/validator test, `.gitignore`, and optionally a safety matrix doc.

**Evidence:** Test gap: `tests/test_smoke.py:24-38` versus OCR tools `glkvm_mcp.py:751-873`; scripts at `scripts/run_ledger.py:44-82`, `scripts/comet_preflight.py:29-48`; image ignores at `.gitignore:30-36`.

**Existing implementation:** Partial smoke tests only.

**Proposed change:** Offline-only PR.

**Unknowns:** Exact schema library.

**Confidence:** High.

## 45. What are the highest-risk assumptions in the current design?

**Answer:** Highest risks are that VLM parse quality will be reliable enough, blocklist detection will be sufficient before Enter, screenshots/WS remain stable through BIOS/reboots, map storage on Comet is writable, hash/fingerprint matching can merge near-duplicate screens safely, and agents will not bypass raw HID tools.

**Evidence:** VLM open questions: `docs/vlm-prompt-contract.md:128-135`; blocklist design: `docs/architecture.md:191-212`; Comet storage unverified: `docs/decisions.md:18-24`; raw tools not policy-gated: `glkvm_mcp.py:400-580`.

**Existing implementation:** Risk mitigations are mostly docs/prose today.

**Proposed change:** Add offline evals, executable policy gates, and live experiments before mutation tools.

**Unknowns:** Real BIOS behavior and VLM performance.

**Confidence:** High.
