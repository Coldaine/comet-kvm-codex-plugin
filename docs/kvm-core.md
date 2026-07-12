# KVM MCP Server Architecture

> **Repo:** `Coldaine/comet-kvm-codex-plugin`
> **Status:** Current product framing for the universal KVM MCP core.

The KVM MCP server is the universal physical-control substrate. The BIOS sidecar is a BIOS-aware orchestration layer (loaded by default; set `COMET_DISABLE_BIOS_SIDECAR=1` to skip) that uses KVM primitives plus VLM grounding, graph state, and visual verification to perform firmware workflows safely and repeatably. Dependency direction is one-way: sidecar may depend on KVM core, not vice versa.

## 1. Overview

The KVM MCP server is a hardened fork of `kennypeh85/glkvm-mcp` that exposes a GL.iNet Comet KVM / GL-RM1 device's keyboard, mouse, screenshot, OCR, and hardware-control capabilities as MCP tools.

It is a stdio MCP server intended to run from `glkvm_mcp.py` with `uv run --script`. The entry point composes universal tools from `src/kvm_core/` and BIOS-aware tools from `src/bios_sidecar/` (loaded by default; `COMET_DISABLE_BIOS_SIDECAR=1` skips sidecar registration) against one shared MCP server. The KVM core owns the physical session; the sidecar delegates to it rather than duplicating transport state.

## 2. Connection Model

The server opens one physical I/O session to the Comet.

| Channel | Purpose |
|---------|---------|
| HTTP(S) | Authentication, screenshots, sysinfo, ATX, MSD upload |
| WebSocket | Keyboard, mouse, and ping frames |

Connections are per-session. `kvm_connect(host, password?, username="admin")` accepts an explicit password or resolves `COMET_PASSWORD` (with `GLCOMET_ADMIN_PASSWORD` as a legacy fallback) from the MCP process environment. The bundled launcher injects the secret with Doppler; the server does not persist it.

TLS verification is disabled because the Comet ships with a self-signed certificate. The expected operating model is trusted LAN access, or remote access through Tailscale/VPN rather than direct public exposure.

## 3. Background Loops

Two background loops are part of the core KVM reliability model.

| Loop | Cadence | Purpose |
|------|---------|---------|
| Stale key watchdog | 40ms | Force-releases keys held longer than 250ms to recover from interrupted input sequences. |
| WebSocket pinger | 1s | Keeps the kvmd WebSocket alive so the Comet does not drop the input channel. |

These loops are firmware-workaround infrastructure, not optional BIOS policy.

## 4. Input Protocol

Keyboard input uses W3C KeyboardEvent codes over the Comet/PiKVM WebSocket API.

Patterns to preserve:

- Atomic key press: `keydown -> 25ms -> keyup(finish=true)`. This mitigates the firmware <= 1.9.0 stuck-key / double-typing bug.
- Modifier wrapping: `mods down -> key down -> key up -> mods up`. This preserves proper modifier release order and addresses `gl-inet/glkvm#22`.
- US keymap and aliases: human-readable key names are resolved to W3C codes before transmission.
- Mouse movement supports PiKVM normalized absolute coordinates and percentage coordinates.
- Mouse clicks and wheel scrolls are raw physical input primitives; they do not know what UI is under the pointer.

## 5. Screenshot and OCR Pipeline

The KVM core exposes frame capture and OCR as general-purpose primitives.

| Tool | Purpose |
|------|---------|
| `kvm_screenshot` | Captures a JPEG frame and returns MCP `Image` content. Supports preview/max-width/quality controls. |
| `kvm_screenshot_to_file` | Captures a frame and stores it under the screenshot cache directory. |
| `kvm_ocr_status` | Reports native Comet OCR state plus host Tesseract availability. |
| `kvm_ocr_text` | Uses native Comet OCR when enabled, else host Tesseract; returns text/lines and supports crop/language parameters. `psm` applies to host fallback only. |
| `kvm_ocr_screenshot` | Runs host Tesseract, returning ordered `text`/`lines` plus word coordinates and confidence. |
| `kvm_ocr_click` | Finds text with OCR and clicks the highest-confidence match. Supports quadrant filtering with `top-left`, `top-right`, `bottom-left`, and `bottom-right`. |

`kvm_screenshot_to_file` uses path safety validation: only filenames or relative paths under the screenshot cache are accepted. Absolute paths and `..` escapes are rejected.

The KVM core has no screen semantics. It sends input, captures frames, runs OCR, and exposes Comet hardware APIs. It does not know whether the screen is BIOS, Windows, an installer, a shell, a crash screen, POST, recovery UI, or anything else.

Native text OCR reuses the Comet/PiKVM `/api/streamer/ocr` capability endpoint and the snapshot endpoint's `ocr`, language, and crop parameters. The endpoint returns text but no word boxes. When native OCR is disabled or fails, the same tool captures a frame and uses Pillow plus pytesseract's spacing-preserving text output. Structured/click OCR uses pytesseract's TSV/dictionary output for boxes and confidence. Host Tesseract calls have a 15-second timeout and run in a worker thread so OCR cannot block the asyncio watchdog and pinger.

## 6. Comet Hardware Tools

The server exposes Comet-specific hardware APIs in addition to HID and screenshots.

| Tool | Purpose | Caution |
|------|---------|---------|
| `comet_atx_power(action)` | Power on/off/reset through the ATX add-on board. | Requires the ATX add-on board to be physically installed. Destructive. |
| `comet_atx_click(button)` | Momentary power/reset button pulse. | Requires the ATX add-on board to be physically installed. Destructive. |
| `comet_sysinfo()` | Reads device metadata and capabilities. | Read-only. |
| `comet_msd_upload(remote_path, local_path)` | Uploads a host file to the Comet's `/userdata/media/` partition. | Writes to device storage. |

ATX endpoints being exposed does not guarantee the target machine is wired for ATX control. The hardware board and cable path still need to exist.

## 7. Tool Annotations

MCP tool annotations are metadata, not an approval system.

Use and keep these annotations:

- `readOnlyHint`
- `destructiveHint`
- `idempotentHint`

These hints tell the client and operator what a tool can do. They do not grant or deny authority, do not create approval tokens, and do not replace operator judgment.

Read-only examples: `kvm_screenshot`, `kvm_screenshot_to_file`, `kvm_ocr_screenshot`, `kvm_status`, `comet_sysinfo`.

Destructive or physical-input examples: `kvm_send_text`, `kvm_send_keys`, `kvm_hold_key`, mouse tools, `kvm_ocr_click`, `comet_atx_power`, `comet_atx_click`, `comet_msd_upload`.

## 8. Security Model

The security model is intentionally narrow.

- LAN-first operation.
- Per-session password supplied through `kvm_connect` or injected as `COMET_PASSWORD`.
- No stored Comet password in the repository.
- TLS verification disabled for the Comet's self-signed certificate.
- Remote operation should use Tailscale or a VPN.
- Do not expose MCP stdio or the Comet HTTP/WebSocket APIs directly to untrusted networks.

Host, username, and LAN IP are non-sensitive in this repo. `COMET_PASSWORD` is the secret and is managed through Doppler.

## 9. Command Output Delivery

An agent receives ordinary MCP tool results directly. It does not need to inspect the runtime log or manually interpret an image when text OCR is sufficient.

### Current pixel-console flow

1. Call `kvm_connect(host)`.
2. Call `kvm_ocr_status()` once, then `kvm_ocr_text()` to establish the current prompt.
3. Call `kvm_send_text(command)` and `kvm_send_keys("Enter")`.
4. Call `kvm_ocr_text()` and read its returned `text` or `lines` fields.
5. Repeat the OCR read only if the command is still updating the visible screen.

This is appropriate for BIOS, recovery, network-down hosts, and other pixel-only states. It cannot recover bytes that scrolled off the HDMI viewport before a frame was captured, and OCR cannot provide a trustworthy process exit status by itself.

### Planned bounded command observer

`kvm_terminal_run` is **Planned** as a single bounded call that sends one command, polls only while that command is active, accumulates visible OCR deltas, and returns the transcript before discarding it. It should use a shell-specific start/end marker where possible, crop to the terminal region, avoid rerunning OCR when the frame is unchanged, and report uncertainty or truncation rather than silently inventing completeness.

An always-on transcript buffer is **Deferred**. Persistent background OCR would add cost, retain potentially sensitive shell text, and still fail to guarantee capture of fast scrollback.

### Candidate exact-output transport

Direct target SSH is a **Candidate** companion component for hosts reachable over the network. It should use AsyncSSH to return exact stdout, stderr, exit status, and timeout state; enforce known-host verification and host allowlisting; and keep target credentials separate from the Comet credential. It is not part of the universal KVM core because it disappears precisely when BIOS, recovery, or network failure makes KVM necessary.

`kvm_ocr_text` implements the Comet/PiKVM OCR endpoint as the preferred text-only path when the device reports it enabled, with automatic host fallback. The live device reported native OCR disabled on 2026-07-10, so host Tesseract is currently selected there. Host OCR remains necessary for word coordinates even when device text OCR is available.

MCP resources or resource-updated notifications may mirror a current transcript for clients that subscribe, but the portable primary interface remains an explicit tool result. Logging is diagnostic only and must not capture commands or OCR text.

## 10. KVM and Sidecar Boundary

The product boundary is engine vs. steering.

| Analogy | Tools | Meaning |
|---------|-------|---------|
| Engine / tires | `kvm_*`, `comet_*` | Universal physical I/O. Sends signals without knowing screen meaning. |
| Steering / navigation | `bios_*` | BIOS-specific orchestration, graph state, and verification. |
| Camera / eyes | Screenshot, OCR, VLM | Perception inputs that can be used by downstream workflows. |

The KVM core does not know about VLMs. It exposes screenshots, OCR, HID, and Comet hardware APIs. A downstream sidecar may call those tools and may use a VLM to interpret screenshots.

### Interaction Lifecycle

| Phase | Tool Call | Layer | Position Tracker Role |
|:---|:---|:---|:---|
| **I. KVM session** | `kvm_connect()` | Universal KVM | Idle. Opens physical I/O session. |
| **II. General triage** | `kvm_ocr_text()` | Universal KVM | Native-first visible text for shells, POST, recovery, and other text screens. |
| | `comet_atx_power("reset")` | Universal KVM | No BIOS semantics. Physical power action. |
| **III. BIOS entry** | `kvm_hold_key("Delete")` or repeated `kvm_send_keys("Delete")` | Universal KVM | Still mostly passive. Getting into setup. |
| **IV. BIOS alignment** | `bios_observe_state()` | BIOS sidecar | Wakes up. Uses screenshot/OCR/VLM to set `current_state`. |
| **V. BIOS cartography** | `bios_crawl_region(...)` | BIOS sidecar | Takes the wheel. Enumerates safe BIOS tree. |
| **VI. BIOS navigation** | `bios_navigate_to(target_node_id="...")` | BIOS sidecar | Replays a graph path and verifies each transition. |
| **VII. BIOS mutation** | `bios_apply_setting_change(capability_id=..., desired_value=...)` | BIOS sidecar | Verifies row, opens selector, uses VLM to read options, changes visible value. |
| **VIII. Save/reboot** | `bios_save_and_reboot()` | BIOS sidecar | **Visually verifies** save dialog before confirming. Verification, not approval. |
| **IX. Evidence** | `bios_export_trace()` | BIOS sidecar | Packages screenshots, parses, transitions, and actions. |
| **X. Close** | `kvm_disconnect()` | Universal KVM | Ends physical session. |

Current design: `kvm_*` remains raw; `bios_*` wraps and verifies. The driver chooses the correct layer.

Future optional design: a deliberate BIOS-active middleware could warn or block raw input during sidecar sessions. That interception does not exist today, so docs should not imply raw `kvm_*` calls are automatically state-checked.

Visual verification stays. Approval-gating is cut. For example, `bios_save_and_reboot` verifying a confirmation dialog before pressing Enter is screen-state verification, not human approval-token policy.

## 11. Known Gaps and Improvement Opportunities

1. **Bounded terminal command observation:** The current OCR primitive returns visible text, but no composite call yet captures screen changes for the duration of a command or reports truncation/uncertainty.
2. **Exact target shell:** No optional AsyncSSH companion exists, so exact stdout/stderr/exit status is unavailable through this project even when the controlled OS is network-reachable.
3. **`comet_raw_*` aliases:** The 10 aliases duplicate `kvm_*` tools. They remain for compatibility and are deprecated in documentation.
4. **Non-OCR operation timeouts:** HTTP requests have a client timeout and OCR has a Tesseract timeout, but some multi-step WebSocket and BIOS operations still lack an overall tool deadline.
5. **Behavioral coverage:** Current tests cover registration, OCR output, logging, state identity, graph transitions, crawl safety, capabilities, and VLM routing. More live/protocol fixtures are still needed for watchdog recovery, pinger failure, OCR quadrant filtering, and ATX error mapping.
