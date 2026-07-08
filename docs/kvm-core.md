# KVM MCP Server Architecture

> **Repo:** `Coldaine/comet-kvm-codex-plugin`
> **Status:** Current product framing for the universal KVM MCP core.

The KVM MCP server is the universal physical-control substrate. The BIOS sidecar is an optional BIOS-aware orchestration layer that uses KVM primitives plus VLM grounding, graph state, and visual verification to perform firmware workflows safely and repeatably.

## 1. Overview

The KVM MCP server is a hardened fork of `kennypeh85/glkvm-mcp` that exposes a GL.iNet Comet KVM / GL-RM1 device's keyboard, mouse, screenshot, OCR, and hardware-control capabilities as MCP tools.

It is a stdio MCP server intended to run from `glkvm_mcp.py` with `uv run --script`. That deployment shape keeps the server easy to add to Codex, Claude Code, Cursor, Kilo, VS Code/Copilot, or any MCP-compatible client.

The current implementation also imports the BIOS sidecar runtime. That is a known architecture gap, not the intended product boundary. See [Known Gaps](#10-known-gaps-and-improvement-opportunities).

## 2. Connection Model

The server opens one physical I/O session to the Comet.

| Channel | Purpose |
|---------|---------|
| HTTP(S) | Authentication, screenshots, sysinfo, ATX, MSD upload |
| WebSocket | Keyboard, mouse, and ping frames |

Connections are per-session. The operator provides the password to `kvm_connect(host, password, username="admin")`; the server does not store credentials.

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
| `kvm_ocr_screenshot` | Captures a frame and runs Tesseract OCR, returning text elements with coordinates and confidence. |
| `kvm_ocr_click` | Finds text with OCR and clicks the highest-confidence match. Supports quadrant filtering with `top-left`, `top-right`, `bottom-left`, and `bottom-right`. |

`kvm_screenshot_to_file` uses path safety validation: only filenames or relative paths under the screenshot cache are accepted. Absolute paths and `..` escapes are rejected.

The KVM core has no screen semantics. It sends input, captures frames, runs OCR, and exposes Comet hardware APIs. It does not know whether the screen is BIOS, Windows, an installer, a shell, a crash screen, POST, recovery UI, or anything else.

Known improvement: OCR currently lives under `src/bios_sidecar/perception/`. It should move into the KVM core package when the dependency inversion is corrected.

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
- Per-session password supplied through `kvm_connect`.
- No stored Comet password in the repository.
- TLS verification disabled for the Comet's self-signed certificate.
- Remote operation should use Tailscale or a VPN.
- Do not expose MCP stdio or the Comet HTTP/WebSocket APIs directly to untrusted networks.

Host, username, and LAN IP are non-sensitive in this repo. `COMET_PASSWORD` is the secret and is managed through Doppler.

## 9. KVM and Sidecar Boundary

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
| **II. General triage** | `kvm_ocr_screenshot()` | Universal KVM | Passive, if active at all. Useful for Windows, POST, recovery, etc. |
| | `comet_atx_power("reset")` | Universal KVM | No BIOS semantics. Physical power action. |
| **III. BIOS entry** | `kvm_hold_key("Delete")` or repeated `kvm_send_keys("Delete")` | Universal KVM | Still mostly passive. Getting into setup. |
| **IV. BIOS alignment** | `bios_observe_state()` | BIOS sidecar | Wakes up. Uses screenshot/OCR/VLM to set `current_state`. |
| **V. BIOS cartography** | `bios_crawl_region(...)` | BIOS sidecar | Takes the wheel. Enumerates safe BIOS tree. |
| **VI. BIOS navigation** | `bios_navigate_to(capability_id="cpu_lite_load_mode")` | BIOS sidecar | Replays graph path and verifies each transition. |
| **VII. BIOS mutation** | `bios_apply_setting_change(capability_id=..., desired_value=...)` | BIOS sidecar | Verifies row, opens selector, uses VLM to read options, changes visible value. |
| **VIII. Save/reboot** | `bios_save_and_reboot()` | BIOS sidecar | **Visually verifies** save dialog before confirming. Verification, not approval. |
| **IX. Evidence** | `bios_export_trace()` | BIOS sidecar | Packages screenshots, parses, transitions, and actions. |
| **X. Close** | `kvm_disconnect()` | Universal KVM | Ends physical session. |

Current design: `kvm_*` remains raw; `bios_*` wraps and verifies. The driver chooses the correct layer.

Future optional design: a deliberate BIOS-active middleware could warn or block raw input during sidecar sessions. That interception does not exist today, so docs should not imply raw `kvm_*` calls are automatically state-checked.

Visual verification stays. Approval-gating is cut. For example, `bios_save_and_reboot` verifying a confirmation dialog before pressing Enter is screen-state verification, not human approval-token policy.

## 10. Known Gaps and Improvement Opportunities

1. **Dependency inversion:** The biggest current gap is that `glkvm_mcp.py` imports `mcp` and `get_runtime()` from `src.bios_sidecar.mcp.server`, where `FastMCP("glkvm_sidecar")` is defined. Desired direction is `bios_sidecar -> kvm_core`; current direction is `kvm_core/glkvm_mcp.py -> bios_sidecar runtime`.
2. **`comet_raw_*` aliases:** The 10 `comet_raw_*` tools duplicate `kvm_*` tools. They are deprecated in documentation only in this pass. Removal is a future code task, and `tests/test_smoke.py` currently expects `comet_raw_send_keys` and `comet_raw_screenshot`.
3. **Tool timeouts:** Tool calls do not have explicit timeouts. Hung HTTP/WebSocket operations can block indefinitely.
4. **Connection guard duplication:** `_require_client()` style checks are repeated across the tool surface and should be centralized when the core is split cleanly.
5. **KVM-core behavioral tests:** The current KVM core has only a tool-registration smoke test. It needs behavioral tests for key mapping, atomic key press, modifier wrapping, path safety, OCR quadrant filtering, ATX validation, watchdog behavior, and pinger behavior.
6. **Runtime-owned KVM helpers:** `kvm_status` and `kvm_ocr_*` currently depend on sidecar runtime state. They should become self-contained KVM-core capabilities.
7. **PEP 723 dependency drift:** `glkvm_mcp.py` imports the sidecar server, which pulls in dependencies such as `instructor` and `litellm` through the sidecar. Those are present in `pyproject.toml` but not in the PEP 723 metadata block, so `uv run --script ./glkvm_mcp.py` can fail in a script-only environment.
