# Plan: KVM MCP Core Documentation — Author and Enshrine

## Context

This round enshrines the KVM MCP server as the product. The BIOS sidecar is downstream/optional and mostly out of scope. BIOS sidecar implementation and design are out of scope for this round, **except** for documenting the KVM/sidecar boundary and the current dependency inversion.

**The architecture sentence to preserve across all docs:**

> The KVM MCP server is the universal physical-control substrate. The BIOS sidecar is an optional BIOS-aware orchestration layer that uses KVM primitives plus VLM grounding, graph state, and visual verification to perform firmware workflows safely and repeatably.

### What this plan cuts (approval-gating architecture)

- Approval tokens (`bios_grant_human_approval`, `policy/approvals.py`)
- Tiered `comet_raw_*` authority namespace (deprecated in docs only this round)
- Human-approval authority model
- Policy-gating as the sidecar's stated purpose

### What this plan does NOT cut (implementation-level safety — keep all of these)

This distinction must be stated bluntly so a future implementation agent does not delete safety concepts because it sees the word "policy":

- **Tool annotations** (`readOnlyHint`, `destructiveHint`, `idempotentHint`) — these are MCP metadata, not an approval system. **Keep ToolAnnotations. Remove approval/policy architecture.**
- **Path safety** (`_safe_screenshot_path` validation against cache directory)
- **Stale key watchdog** (40ms loop, 250ms force-release)
- **Visual verification** (e.g., `bios_save_and_reboot` checking the confirm dialog is on screen before pressing Enter — this is **screen-state verification**, NOT approval-token policy)
- **Destructive tool labeling** and operator caution in docs

**Policy vs. verification — the most important clarification:**

- Approval-gating = cut. A human grants a token; the driver cannot act without it. Gone.
- Visual verification = stays. The sidecar takes a screenshot, confirms the expected screen/dialog is present, then proceeds. This is the sidecar making BIOS interaction safer, not an authority system.

Example: `bios_save_and_reboot` verifying a confirmation dialog is visible before hitting Enter is **not** an approval system. It is screen-state verification. Do not let an agent remove dialog checks, OCR checks, or screenshot confirmation because it sees the word "policy."

### Scope guardrails (prevent destructive interpretation)

This is a **documentation-only plan**. Explicitly:

- No source code changes.
- No source deletion.
- No sidecar file deletion.
- No VLM contract deletion.
- No tool removal (including `comet_raw_*` aliases — deprecate in docs only).
- Only documentation edits.

`comet_raw_*` aliases are deprecated in documentation only in this round; removal is a later code-change task.

---

## The KVM/sidecar boundary (engine vs. steering)

This goes in `docs/kvm-core.md` and defines the boundary the docs must communicate.

**Engine / tires:** `kvm_*` and `comet_*` tools. Universal. First-class. No BIOS semantics. They send signals without knowing what's on screen.

**Steering / navigation:** `bios_*` tools. BIOS-specific. Stateful. VLM-grounded. Verification-wrapped.

**Camera / eyes:** screenshot + OCR + VLM. Used by the sidecar to understand where the steering is pointed.

### The interaction lifecycle (revised — document this table in the boundary section)

| Phase | Tool Call | Layer | Position Tracker Role |
|:---|:---|:---|:---|
| **I. KVM session** | `kvm_connect()` | Universal KVM | Idle. Opens physical I/O session. |
| **II. General triage** | `kvm_ocr_screenshot()` | Universal KVM | Passive, if active at all. Useful for Windows, POST, recovery, etc. |
| | `comet_atx_power("reset")` | Universal KVM | No BIOS semantics. Physical power action. |
| **III. BIOS entry** | `kvm_hold_key("Delete")` or repeated `kvm_send_keys("Delete")` | Universal KVM | Still mostly passive. Getting into setup. |
| **IV. BIOS alignment** | `bios_observe_state()` | BIOS sidecar | Wakes up. Uses screenshot/OCR/VLM to set `current_state`. |
| **V. BIOS cartography** | `bios_crawl_region(...)` | BIOS sidecar | Takes the wheel. Enumerates safe BIOS tree. |
| **VI. BIOS navigation** | `bios_navigate_to(capability_id="cpu_lite_load_mode")` | BIOS sidecar | Replays graph path and verifies each transition. |
| **VII. BIOS mutation** | `bios_apply_setting_change(capability_id=..., desired_value=...)` | BIOS sidecar | Verifies row, opens selector, uses VLM to read options, changes visible value. |
| **VIII. Save/reboot** | `bios_save_and_reboot()` | BIOS sidecar | **Visually verifies** save dialog before confirming. (Verification, not approval.) |
| **IX. Evidence** | `bios_export_trace()` | BIOS sidecar | Packages screenshots, parses, transitions, and actions. |
| **X. Close** | `kvm_disconnect()` | Universal KVM | Ends physical session. |

### Corrections to the lifecycle that the docs must reflect

1. **`kvm_connect`, not `bios_connect`.** The physical session is KVM-level. There should not be a separate `bios_connect` unless it means "attach BIOS tracker to an existing KVM session." If lifecycle state is needed later, name it `bios_begin_run` / `bios_attach_session` / `bios_start_cartography` — not `bios_connect`.

2. **`bios_apply_setting_change` uses a capability ID, not a fuzzy label.** The tool contract is canonical (`capability_id="cpu_lite_load_mode"`, `desired_value="Mode 3"`). The sidecar may resolve aliases ("Lite Load", "CPU Lite Load") but the tool surface is canonical.

3. **`kvm_match_screen()` is internal/debug, not a driver workflow step.** The driver calls `bios_navigate_to(...)`; the sidecar internally calls `kvm_match_screen` / OCR hash / VLM fallback. `kvm_match_screen()` can exist as a debug/developer tool, but the high-level driver workflow should not need it.

4. **No interception of raw `kvm_*` calls.** Do NOT claim the sidecar intercepts raw `kvm_*` calls unless that mode is deliberately implemented. The correct framing: BIOS workflows enter through `bios_*` tools, which internally use `kvm_*` primitives. Raw `kvm_*` tools remain available for universal/manual/debug use but do not automatically participate in BIOS state verification.

   Two possible designs (document the first as current, the second as future-optional):

   | Design | Behavior |
   |--------|----------|
   | **Recommended now** | `kvm_*` remains raw; `bios_*` wraps and verifies. Driver chooses correct layer. |
   | **Future optional** | Server has a "BIOS active mode" middleware that warns/blocks raw input during sidecar sessions. |

### Where the VLM fits (sidecar-internal — keep out of KVM-core architecture)

For `docs/kvm-core.md`, say only: *The KVM core does not know about VLMs. It exposes screenshots/OCR/HID. A downstream sidecar may call those tools and may use a VLM to interpret screenshots.* Do not describe the VLM in detail in the KVM-core doc except in the boundary section.

The VLM (documented in sidecar-scoped docs, not KVM-core) helps with:
1. Initial screen classification
2. BIOS tree enumeration
3. Row/value extraction
4. Selected-row detection
5. Dropdown/modal parsing
6. Drift recovery
7. Before/after verification
8. Save confirmation verification

The VLM does NOT: send keys, decide hardware policy, replace the KVM core, replace the position tracker, or replace the driver agent.

---

## Findings from code inspection

### Structural inversion (the biggest architecture gap)

The KVM core depends on the sidecar, not the other way around:
- `glkvm_mcp.py:28` imports `mcp, get_runtime` from `src.bios_sidecar.mcp.server` — the FastMCP instance is defined inside the sidecar
- The transport layer (`CometClient`, `CaptureManager`) lives in `src/bios_sidecar/comet/` — inside the sidecar package
- `OCRManager` lives in `src/bios_sidecar/perception/` — inside the sidecar package
- 9 call sites in `glkvm_mcp.py` call `get_runtime()` to access the sidecar's singleton
- `kvm_status` (a pure KVM-core tool) reads client state via `get_runtime()` — can't function without the sidecar
- `kvm_ocr_screenshot` and `kvm_ocr_click` use `get_runtime().ocr_mgr` — OCR is sidecar-owned

**Desired dependency:** `bios_sidecar → kvm_core`
**Current dependency:** `kvm_core/glkvm_mcp.py → bios_sidecar runtime`

This is backwards for the product framing. Document as the **first known gap** in `docs/kvm-core.md` and mention in `architecture.md`.

### AGENTS.md is stale about ATX

AGENTS.md:36 says "ATX power control: Not available... not wrapped in MCP tools yet." But `glkvm_mcp.py:260-270` wraps `comet_atx_power` and `comet_atx_click`. The "BIOS entry workflow (without ATX)" section (AGENTS.md:37) is also stale. ATX IS available and wrapped.

### Test claim is inverted

6 test files exist. 5 are sidecar tests. 1 is KVM-core (`test_smoke.py` — tool registration only, no behavioral tests). The KVM core has zero behavioral tests — no tests for key mapping, atomic press patterns, screenshot capture, OCR pipeline, ATX, or the watchdog/pinger loops.

### 10 dead-weight alias tools

`comet_raw_send_text`, `comet_raw_send_keys`, `comet_raw_hold_key`, `comet_raw_release_all`, `comet_raw_mouse_move`, `comet_raw_mouse_move_pct`, `comet_raw_mouse_click`, `comet_raw_mouse_scroll`, `comet_raw_screenshot`, `comet_raw_status` — pure duplicates of their `kvm_*` counterparts. D11 artifact. Deprecated in docs only this round.

### The unique tool surface (18 tools, excluding aliases)

| Category | Tools |
|----------|-------|
| Connection | `kvm_connect`, `kvm_disconnect`, `kvm_status` |
| Keyboard | `kvm_send_text`, `kvm_send_keys`, `kvm_hold_key`, `kvm_release_all` |
| Mouse | `kvm_mouse_move`, `kvm_mouse_move_pct`, `kvm_mouse_click`, `kvm_mouse_scroll` |
| Screenshot/OCR | `kvm_screenshot`, `kvm_screenshot_to_file`, `kvm_ocr_screenshot`, `kvm_ocr_click` |
| Comet hardware | `comet_atx_power`, `comet_atx_click`, `comet_sysinfo`, `comet_msd_upload` |

---

## Documentation to author

### 1. NEW: `docs/kvm-core.md` — KVM MCP Server Architecture

Primary deliverable. Treats the KVM core as a designed product.

**Sections:**

1. **Overview** — what the KVM MCP server is: a hardened fork of glkvm-mcp exposing a GL.iNet Comet (PiKVM-fork) device's keyboard, mouse, screenshot, and OCR capabilities as MCP tools. Stdio MCP server via PEP 723 + `uv run --script`. Works in any MCP client.

2. **Connection model** — HTTP for screenshots + auth, WebSocket for keyboard/mouse. Single persistent connection. Per-session password (no stored credentials). TLS disabled (self-signed cert).

3. **Background loops** (patterns to enshrine):
   - Stale key watchdog (40ms period, 250ms threshold, force-releases stuck keys)
   - WebSocket pinger (1s interval, prevents kvmd timeout)

4. **Input protocol** (patterns to enshrine):
   - Atomic key press: `keydown → 25ms → keyup(finish=true)`. Fixes firmware <= 1.9.0 stuck-key bug.
   - Modifier wrapping: `mods down → key down → key up → mods up`. Fixes gl-inet/glkvm #22.
   - W3C KeyboardEvent codes with US keymap. Key aliases resolve human-readable names.
   - Mouse: absolute int16 or percentage coordinates. Button press/release, wheel scroll.

5. **Screenshot/OCR pipeline** (patterns to enshrine + improve):
   - `kvm_screenshot` — JPEG with preview/max_width/quality. Returns MCP `Image`.
   - `kvm_screenshot_to_file` — capture + save with **path safety** validation.
   - `kvm_ocr_screenshot` — Tesseract OCR. Returns text elements with coordinates + confidence.
   - `kvm_ocr_click` — find text via OCR, **filter by screen quadrant**, click highest-confidence match.
   - Improvement needed: OCR manager currently lives in the sidecar. Should be part of the KVM core.

6. **Comet hardware tools** — `comet_atx_power`, `comet_atx_click`, `comet_sysinfo`, `comet_msd_upload`. Note: requires ATX add-on board physically installed.

7. **Tool annotations** — every tool carries `readOnlyHint`/`destructiveHint`/`idempotentHint`. Document which tools are read-only vs destructive. **Keep these — they are metadata, not an approval system.**

8. **Security model** — LAN only, TLS disabled, per-session password, remote via Tailscale/VPN.

9. **The KVM/sidecar boundary** — the engine/steering/camera analogy + the interaction lifecycle table (above). State the architecture sentence. State: the KVM core has no screen semantics — it sends input, captures frames, runs OCR, and exposes Comet hardware APIs. It does not know whether the screen is BIOS, Windows, installer, shell, or recovery UI. The VLM is sidecar-internal; the KVM core does not know about VLMs.

10. **Known gaps and improvement opportunities** (see below).

### 2. UPDATE: `AGENTS.md`

- Fix ATX claim (lines 36-37): ATX IS wrapped. Remove "not available" and "not wrapped."
- Remove policy/approval framing.
- Reframe three-agent topology (lines 9-21): keep developer + driver roles. The "VLM agent" is a tool the sidecar calls, not a peer role.
- Point at `docs/kvm-core.md` for KVM-core architecture.

### 3. UPDATE: `decisions.md`

**Add KVM-core decisions:**
- D-K1: KVM tool surface (18 unique tools; `comet_raw_*` aliases deprecated in docs)
- D-K2: ATX power control (IS wrapped — supersedes AGENTS.md claim)
- D-K3: Upstream sync (fetch-only, selective cherry-pick — moved from AGENTS.md)
- D-K4: Watchdog + pinger (firmware-bug workarounds, not optional)
- D-K5: Security model (LAN only, TLS disabled, per-session password)
- D-K6: PEP 723 single-file server (uv run --script deployment model)

**Sidecar decision cleanup:**
- D10, D11: note as **REMOVED**
- D8 (workflow phase ledger): note as **QUESTIONED — user does not understand this concept.** Flag for re-evaluation. Do not enshrine.
- D9: keep existing provisional annotation

### 4. UPDATE: `README.md`

- Add Comet hardware tools to the MCP Tools table (currently missing)
- Note `comet_raw_*` aliases as deprecated (docs only)
- Adjust opening framing to lead with the KVM plugin

### 5. UPDATE: `docs/architecture.md`

- §2 ("How glkvm_mcp.py works") becomes a brief summary pointing to `docs/kvm-core.md`
- Mention the dependency inversion as a known architecture gap
- KVM-core content moves to `docs/kvm-core.md`

### 6. Doc tail triage

| Doc(s) | Action |
|--------|--------|
| `docs/remediation/R1-R16` | Reference cut D10/D11. Mark superseded in `docs/remediation/README.md`. |
| `docs/communication-audits/01-04` | Historical. Mark superseded. |
| `docs/plans/01-vlm-mcp-integration-plan.md` | References D10/D11. Supersede or rewrite. |
| `docs/vlm-prompt-contract.md` | Still relevant. Reframe as sidecar-internal. |
| `docs/reference/comet-hardware.md` | Unaffected. |
| `docs/reference/comet-api.md` | Unaffected. |

---

## Patterns to enshrine (in `docs/kvm-core.md`)

1. Atomic key press (`keydown → 25ms → keyup(finish=true)`)
2. Modifier wrapping order (`mods down → key down → key up → mods up`)
3. Stale key watchdog (40ms loop, 250ms force-release)
4. WebSocket pinger (1s ping interval)
5. Screenshot path safety (`_safe_screenshot_path` validation)
6. OCR click with quadrant filtering
7. PEP 723 + uv run (zero-setup deployment)
8. Tool annotations (`readOnlyHint`/`destructiveHint`/`idempotentHint` — metadata, not approval)

## Patterns to improve (in `docs/kvm-core.md` §10 — Known Gaps)

1. **Dependency inversion** (first/most important) — KVM core imports from sidecar. Should be reversed.
2. **Remove `comet_raw_*` aliases** — 10 duplicate tools. Deprecated in docs this round; code removal is later.
3. **Add tool timeouts** — no tool has a `timeout`. Hung calls block indefinitely.
4. **Centralize the connection guard** — `_require_client()` repeated 20+ times.
5. **KVM-core behavioral tests** — only a smoke test exists. Needs tests for key mapping, atomic press, modifier wrapping, path safety, OCR quadrant filtering, ATX validation.
6. **`kvm_status` and `kvm_ocr_*` depend on sidecar runtime** — should be self-contained. Resolves automatically if dependency inversion is fixed.

---

## Things to remove from docs (documentation edits only — no code changes)

1. Policy/approval layer framing — no authority doc frames the sidecar as "policy-gated authority."
2. Workflow phase ledger (D8) — mark questioned, do not enshrine.
3. Three-agent topology "VLM agent" as peer role — keep developer + driver only.
4. `bios_connect` from the mental model — `kvm_connect` is the physical session.

## Things to keep (do NOT remove — safety, not policy)

1. Tool annotations (`readOnlyHint`, `destructiveHint`, `idempotentHint`)
2. Path safety validation
3. Stale key watchdog
4. Visual verification (screen-state checks before proceeding)
5. Destructive tool labeling and operator caution

---

## Validation

After the documentation is authored:
- [ ] `docs/kvm-core.md` exists and documents the KVM MCP server as a designed product
- [ ] `docs/kvm-core.md` explicitly says the KVM core has no screen semantics: it sends input, captures frames, runs OCR, and exposes Comet hardware APIs. It does not know whether the screen is BIOS, Windows, installer, shell, or recovery UI.
- [ ] `docs/kvm-core.md` states the architecture sentence (KVM core = universal substrate; sidecar = optional BIOS-aware orchestration)
- [ ] `docs/kvm-core.md` includes the engine/steering/camera analogy and the interaction lifecycle table
- [ ] `docs/kvm-core.md` does NOT describe the VLM in detail (only the boundary mention)
- [ ] `docs/kvm-core.md` documents the 8 enshrined patterns and 6 improvement opportunities
- [ ] AGENTS.md no longer claims ATX is unwrapped
- [ ] AGENTS.md no longer frames the VLM as a peer agent role
- [ ] AGENTS.md points at `docs/kvm-core.md` for KVM-core architecture
- [ ] decisions.md has KVM-core decisions (D-K1 through D-K6)
- [ ] decisions.md marks D8 as questioned, notes D10/D11 as removed
- [ ] README.md tool table includes `comet_atx_power`, `comet_atx_click`, `comet_sysinfo`, `comet_msd_upload`
- [ ] README.md notes `comet_raw_*` aliases as deprecated (docs only)
- [ ] `docs/architecture.md` §2 points to `docs/kvm-core.md`, mentions dependency inversion
- [ ] No authority doc enshrines the policy/approval layer or the workflow phase ledger
- [ ] The policy-vs-verification distinction is stated bluntly in the plan and reflected in docs
- [ ] The test gap (1 smoke test for KVM core, 5 behavioral tests for sidecar) is documented
- [ ] The structural dependency inversion is documented as the first known gap
- [ ] No source code, sidecar files, VLM docs, or tools were deleted (docs-only pass)
