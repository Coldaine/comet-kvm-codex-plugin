# Comet KVM API & Software Surface Reference

> **Repo:** `Coldaine/comet-kvm-codex-plugin` (fork of `kennypeh85/glkvm-mcp`)
> **Status:** Verified from `glkvm_mcp.py` source code, GL.iNet docs, and GitHub issues.
> **Compiled:** 2026-07-07
> **Purpose:** Document the API surface the Comet exposes, what this project currently exercises, known firmware bugs and workarounds, and the boundary between transport and stateful logic.

## Architecture Overview

```
┌──────────────┐     MCP stdio      ┌─────────────────┐     HTTPS/WSS     ┌──────────┐
│  AI Agent    │ ◄─────────────────► │  glkvm_mcp.py   │ ◄───────────────► │  Comet   │
│ (Codex/LLM)  │    tool calls       │  (MCP server)   │   (PiKVM API)     │  (GL-RM1)│
└──────────────┘                     └─────────────────┘                   └──────────┘
                                             │
                                      kvm_ocr_text
                                             │
                    ┌────────────────────────┴────────────────────────┐
                    ▼                                                 ▼
         Native OCR (Comet)                              Host Tesseract
         /api/streamer/ocr                               (pytesseract)
                    │                                                 ▲
                    └── disabled / fail ──── fallback ────────────────┘
```

The MCP server uses `glkvm_mcp.py` as a PEP 723 composition entry point and keeps implementation under `src/kvm_core/` and `src/bios_sidecar/`. It is launched via `uv run --locked --python 3.13 python ./glkvm_mcp.py` and runs over stdio. The KVM core maintains a persistent WebSocket connection to the Comet for low-latency input and uses HTTP for screenshots and authentication.

> **Source:** `glkvm_mcp.py` (PEP 723 metadata and composition), `src/kvm_core/server.py`, and `src/kvm_core/runtime.py`. Verified 2026-07-10.

## API Endpoints (PiKVM-Fork)

The Comet runs a PiKVM-fork firmware. The API surface is PiKVM-compatible. The project currently implements or probes the following endpoint groups.

### 1. Authentication: `POST /api/auth/login`

```
POST /api/auth/login
Form body: user=admin&passwd=<password>&expire=0
Response: Sets `auth_token` cookie; may return `two_step_required` for 2FA
```

- Default username: `admin`
- Password is passed per-session via `kvm_connect`, or fetched from Doppler CLI (`COMET_PASSWORD` in `doppler.yaml`'s project/config) — never from process environment, never stored server-side
- The client stores the cookie token and sends it as the HTTP `Token` header on subsequent requests
- WebSocket auth uses `Cookie: auth_token=...` and `Token` headers (not a query-string token)
- Clean disconnect calls `POST /api/auth/logout`

> **Source:** `src/kvm_core/comet/client.py` (`CometClient.connect` / `disconnect`). Verified against PiKVM/GLKVM handbook 2026-07-15.

### 2. Keyboard/Mouse: `WSS /api/ws?stream=false`

WebSocket connection for real-time input:
- `stream=false` — video stream is not carried over WebSocket; screenshots use the HTTP snapshot endpoint instead
- Keyboard events: keydown, keyup (with `finish=true` flag)
- Mouse events: button press/release, absolute move (int16 coordinates), wheel scroll
- Application ping: `{"event_type":"ping","event":{}}` (the `event` object is required)
- A receiver task drains server events (`*_state`, `pong`, `kickout`) and caches the latest subsystem state
- Intentional `kvm_hold_key` holds are watchdog-protected until their release deadline

> **Source:** PiKVM handbook WebSocket section; `src/kvm_core/comet/client.py`.

### 3. Screenshot: `GET /api/streamer/snapshot`

```
GET /api/streamer/snapshot?preview=<bool>&preview_max_width=<int>&preview_quality=<int>
Response: JPEG image bytes
```

- Returns a JPEG frame from the HDMI capture
- Parameters control preview mode (downscaled) vs. full-resolution, max width, and JPEG quality
- Used by `kvm_screenshot`, `kvm_screenshot_to_file`, `kvm_ocr_screenshot`, and `kvm_ocr_click` tools

> **Source:** `src/kvm_core/comet/client.py` (`get_screenshot`) and `src/kvm_core/tools.py` (screenshot/OCR tools). Verified 2026-07-10.

### 4. Native OCR: `GET /api/streamer/ocr` and snapshot OCR parameters

`GET /api/streamer/ocr` reports whether device OCR is enabled, its engine (`tesseract` or `rknn`), and default/available languages. When enabled, `GET /api/streamer/snapshot?ocr=true` returns text and accepts `ocr_langs` plus pixel crop coordinates (`ocr_left`, `ocr_top`, `ocr_right`, `ocr_bottom`).

The live device returned HTTP 200 for the capability endpoint on 2026-07-10, with OCR disabled. The OCR snapshot path returned HTTP 500 while disabled. `kvm_ocr_status` and `kvm_ocr_text` wrap these endpoints and use host Tesseract as the automatic fallback.

> **Source:** GL.iNet `kvmd/apps/kvmd/api/streamer.py`, `kvmd/apps/kvmd/ocr.py`, `src/kvm_core/comet/client.py`, and live probes. Verified 2026-07-10.

### Additional implemented or probed endpoints

These endpoints were checked against the target Comet at `192.168.0.126`. Destructive ATX actions and MSD uploads were not invoked during the 2026-07-10 read-only verification.

| Endpoint | Implementation | Live verification | Purpose |
|---|---|---|---|
| `GET /api/info` | `comet_sysinfo` / `comet_capabilities` | Authenticated HTTP 200 on 2026-07-10 | Device metadata, firmware, and hardware info |
| `GET /api/atx` | `comet_power_state` | Endpoint existence only | ATX LED/power state |
| `POST /api/atx/*` | `comet_atx_power`, `comet_atx_click` | Endpoint existence only; action not invoked | ATX power/reset (query params) |
| `GET/POST /api/msd/*` | `comet_media_*`, `comet_msd_upload` | Endpoint existence only; upload not invoked | Virtual media lifecycle |
| `POST /api/gpio/*` | No direct MCP tool | Endpoint existence only | Low-level GPIO for the ATX board |
| `GET /api/wol/*` | `comet_wol_*` | Not yet live-verified | Wake-on-LAN |
| `/redfish/v1/...` | `comet_redfish_power` | Not yet live-verified | Narrow Redfish power facade |

### ATX Power Control (`POST /api/atx/*`)

**Requires the ATX add-on board** — a separate hardware accessory that wires to the motherboard's power/reset headers. Without this board, the API will return an error even when authenticated.

PiKVM/GLKVM ATX uses **query parameters**, not JSON bodies:

- `POST /api/atx/power?action=on|off|off_hard|reset_hard&wait=true`
- `POST /api/atx/click?button=power|power_long|reset&wait=true`
- `GET /api/atx` — read power/LED state

MCP aliases: `reset` → `reset_hard`, `force_off` → `off_hard`.

MCP tools: `comet_power_state`, `comet_atx_power`, `comet_atx_click`.

### Mass Storage (`/api/msd/*`)

Virtual media uses the PiKVM MSD contract:

- `POST /api/msd/write?image=<name>` — raw image body + `Content-Length` (not multipart)
- `POST /api/msd/write_remote?url=...&image=...` — Comet downloads the image
- `POST /api/msd/set_params?image=...&cdrom=true&rw=false`
- `POST /api/msd/set_connected?connected=true|false`
- `GET /api/msd` — state / image list

MCP tools: `comet_media_state`, `comet_media_upload`, `comet_media_fetch`, `comet_media_mount`, `comet_media_unmount`, `comet_media_remove`, `comet_media_reset` (plus legacy `comet_msd_upload`).

### System Info (`GET /api/info`)

Returns device metadata: model, firmware version, serial, hardware capabilities. Connect-time discovery also probes `/api/upgrade/version`, `/api/system/capability`, and subsystem GETs.

MCP tools: `comet_sysinfo`, `comet_capabilities`.

### GPIO (`POST /api/gpio/*`)

Low-level GPIO control for the ATX board. Typically not needed directly — the ATX API wraps GPIO operations.

> **Probe history:** Endpoint existence was confirmed unauthenticated on 2026-07-07; `/api/info` and native OCR state were verified authenticated on 2026-07-10.

## MCP Tools Exposed by the Composed Server

### Connection
| Tool | Signature | Annotations | Description |
|------|-----------|-------------|-------------|
| `kvm_connect` | `(host, password?, username?, target?)` | write, non-destructive, idempotent | Connect to Comet; optional multi-target id |
| `kvm_disconnect` | `(target?)` | write, non-destructive, idempotent | Close one or all sessions |
| `kvm_status` | `(target?)` | read-only, non-destructive, idempotent | Connection state, held keys, WS health |
| `kvm_select_target` | `(target)` | write, non-destructive, idempotent | Select default multi-Comet target |

### Keyboard
| Tool | Signature | Annotations | Description |
|------|-----------|-------------|-------------|
| `kvm_send_text` | `(text, wpm?)` | write, destructive | Type a string (atomic press pattern) |
| `kvm_send_keys` | `(combo)` | write, destructive | Send key chord (e.g. "Ctrl+Alt+Delete") |
| `kvm_hold_key` | `(key, duration_ms)` | write, destructive | Press and hold (for auto-repeat scrolling) |
| `kvm_release_all` | `()` | write, destructive, idempotent | Force-release all held keys |

### Mouse
| Tool | Signature | Annotations | Description |
|------|-----------|-------------|-------------|
| `kvm_mouse_move` | `(x, y)` | write, destructive | Absolute int16 coordinates |
| `kvm_mouse_move_pct` | `(x_pct, y_pct)` | write, destructive | Percentage of screen (0,0 = top-left) |
| `kvm_mouse_click` | `(button?, count?)` | write, destructive | Click at current position |
| `kvm_mouse_scroll` | `(dx?, dy?)` | write, destructive | Scroll wheel |

### Screenshot / OCR
| Tool | Signature | Annotations | Description |
|------|-----------|-------------|-------------|
| `kvm_screenshot` | `(preview?, max_width?, quality?)` | read-only, non-destructive, idempotent | JPEG as MCP image content |
| `kvm_screenshot_to_file` | `(path, preview?, ...)` | read-only, non-destructive, idempotent | Save JPEG to disk |
| `kvm_ocr_status` | `()` | read-only, non-destructive, idempotent | Native OCR state plus host Tesseract status |
| `kvm_ocr_text` | `(psm?, languages?, prefer_native?, left?, top?, right?, bottom?)` | read-only, non-destructive, idempotent | Native-first text OCR with host fallback and optional crop; `psm` configures fallback only |
| `kvm_ocr_screenshot` | `(search_text?, preview?, psm?)` | read-only, non-destructive, idempotent | Capture + Tesseract OCR → ordered text/lines plus word coordinates; `psm=6` suits terminals |
| `kvm_ocr_click` | `(text, button?, count?, search_area?)` | write, destructive | OCR-find text → click it (all-in-one) |

> **Source:** `src/kvm_core/tools.py` (`@mcp.tool` registrations and annotations). Verified 2026-07-10.

### Comet Hardware
| Tool | Signature | Annotations | Description |
|------|-----------|-------------|-------------|
| `comet_power_state` | `(target?)` | read-only | GET `/api/atx` |
| `comet_atx_power` | `(action, wait?, target?)` | write, destructive | Query-param ATX power (`reset`→`reset_hard`) |
| `comet_atx_click` | `(button, wait?, target?)` | write, destructive | `power` / `power_long` / `reset` |
| `comet_sysinfo` | `(target?)` | read-only | Device metadata |
| `comet_capabilities` | `(refresh?, target?)` | read-only | Connect-time capability profile |
| `comet_msd_upload` | `(local_path, image_name?, target?)` | write, destructive | Raw streaming MSD upload |
| `comet_media_*` | — | — | state/upload/fetch/mount/unmount/remove/reset |
| `comet_wol_*` | — | — | list/scan/wake |
| `comet_streamer_*` / `comet_recorder_*` | — | — | stream + recording controls |
| `comet_metrics` | `(target?)` | read-only | Prometheus metrics text |
| `comet_tailscale_status` | `(target?)` | read-only | Tailscale status |
| `comet_redfish_power` | `(reset_type, target?)` | write, destructive | Redfish ComputerSystem.Reset |

### BIOS Workflow (sidecar)
| Tool | Signature | Description |
|------|-----------|-------------|
| `bios_observe_state` | `()` | Capture, parse, and sync current BIOS position |
| `bios_crawl_step` | `()` | Single safe crawl transition (debug) |
| `bios_crawl_region` | `(max_depth?)` | DFS region crawl with cycle detection |
| `bios_navigate_to` | `(target_node_id)` | Replay graph path to target node |
| `bios_propose_setting_change` | `(capability_id, desired_value)` | Plan a setting change |
| `bios_apply_setting_change` | `(capability_id, desired_value)` | Apply mutation with verification |
| `bios_save_and_reboot` | `()` | F10 save with dialog verification, reboot |
| `bios_abort_and_recover` | `()` | Release keys and Escape back-out |
| `bios_export_trace` | `()` | Export replayable run trace JSON |

### Perception (sidecar)
| Tool | Signature | Description |
|------|-----------|-------------|
| `kvm_vlm_parse` | `(screenshot_ref, previous_state_id?, last_action?)` | VLM structured parse of cached screenshot |
| `kvm_match_screen` | `(screenshot_ref, expected_node_id?)` | Local phash + OCR fingerprint graph match |

### MCP Resources (sidecar)
| URI | Returns | Description |
|-----|---------|-------------|
| `bios://state/current` | JSON string | Latest normalized BIOS state |
| `bios://screen/current` | bytes | Current screenshot (known R1c limitation) |
| `bios://graph/current` | JSON string | Navigation graph summary |
| `bios://capabilities/current` | JSON string | Discovered settings index |

See [`docs/kvm-core.md`](../kvm-core.md) for the BIOS interaction lifecycle.

## External References

This document maps **what this MCP server exercises** against the Comet/PiKVM API. It is not the full upstream API reference.

| Source | What it covers |
|--------|----------------|
| [PiKVM API docs](https://docs.pikvm.org/api/) | Canonical PiKVM HTTP/WebSocket API (Comet firmware is a fork) |
| [GL.iNet KVM docs](https://docs.gl-inet.com/kvm/) | Comet product documentation and user guides |
| [gl-inet/glkvm](https://github.com/gl-inet/glkvm) | Firmware source; API handlers under `kvmd/apps/kvmd/api/` |
| [kennypeh85/glkvm-mcp](https://github.com/kennypeh85/glkvm-mcp) | Upstream MCP server this repo forked from (15 `kvm_*` tools) |

## Internal Background Tasks (Asyncio)

The MCP process runs **two background asyncio loops** for transport reliability:

### `_watchdog_loop` (40ms period)
- Monitors held keys
- Force-releases any key still tracked as held after `STALE_S` (250ms)
- Prevents stuck keys from input sequences that were interrupted or failed

### `_pinger_loop` (1s period)
- Sends WebSocket ping frames to keep the connection alive
- Detects dropped connections

> **Source:** `src/kvm_core/comet/client.py` (`_watchdog_loop` and `_pinger_loop`). Verified 2026-07-10.

**Design implication:** These loops are transport reliability mechanisms. The BIOS state tracker remains on demand; it is not an always-on third screenshot/OCR loop. A future bounded terminal observer should poll only for the duration of its active tool call. See `docs/decisions.md` D7 and D-K7.

## Known Firmware Bugs & Workarounds

### Stuck Key / Double-Typing (Firmware ≤ 1.9.0)
- **Bug:** Characters sent rapidly can double-type or get stuck in the down state
- **Fix in `glkvm_mcp.py`:** Every character is sent as an atomic `keydown → 25ms → keyup(finish=true)` pattern
- **Tunables:** `MIN_DOWN_UP_GAP_S = 0.025`, `INTER_CHAR_GAP_S = 0.010`

### Modifier Release Order Bug (gl-inet/glkvm #22)
- **Bug:** Modifiers released in wrong order relative to the main key
- **Fix:** Modifiers wrap strictly outside the main key: `mods down → key down → key up → mods up`

### Stale Key Watchdog
- **Prevention:** Any key held >250ms is auto-released by the watchdog loop
- **Recovery tool:** `kvm_release_all` force-releases everything — should be called after any failed or interrupted input sequence

> **Sources:**
> - `src/kvm_core/comet/client.py` (HID timing fields, atomic press, modifier wrapping, watchdog). Verified 2026-07-10.
> - `README.md#firmware-bug-fixes`. Verified 2026-07-07.

## OCR Integration

Text-only OCR uses the Comet when its native engine is enabled and falls back to the host:

- Tesseract binary is located via `TESSERACT_PATH`/`TESSERACT_CMD` env vars, then `PATH`, then Windows default paths
- `kvm_ocr_status` reads `GET /api/streamer/ocr` and reports native plus host availability
- `kvm_ocr_text` prefers native `GET /api/streamer/snapshot?ocr=true`, passing language and crop parameters; it falls back to host `image_to_string` with preserved inter-word spacing
- `kvm_ocr_screenshot` captures a frame, passes it to Tesseract, and returns structured JSON:
  ```json
  {
    "width": 1920,
    "height": 1080,
    "text": "File Edit",
    "lines": ["File Edit"],
    "elements": [
      {"text": "File", "confidence": 96.3, "x_pct": 5.2, "y_pct": 3.1},
      {"text": "Edit", "confidence": 95.8, "x_pct": 8.7, "y_pct": 3.1}
    ]
  }
  ```
- `kvm_ocr_click` finds text by name and clicks its exact coordinates — eliminates the "vision model estimates pixel position" unreliability
- Pillow supplies decoded image dimensions; pytesseract is bounded to 15 seconds and runs off the MCP asyncio loop

### Device-side OCR capability

GL.iNet's PiKVM fork exposes `GET /api/streamer/ocr` with `enabled`, `engine` (`tesseract` or `rknn`), and language state. `GET /api/streamer/snapshot?ocr=true` returns recognized text and accepts `ocr_langs`, `ocr_left`, `ocr_top`, `ocr_right`, and `ocr_bottom`. `kvm_ocr_text` now normalizes that native response and falls back automatically. On 2026-07-10, the live Comet at `192.168.0.126` returned `enabled: false`, engine `tesseract`, and no available/default languages; the native snapshot call returned HTTP 500, so host Tesseract is selected on that unit. Native OCR does not replace host word boxes used for coordinate-sensitive tools.

> **Source:** `src/kvm_core/ocr.py`, `src/kvm_core/tools.py`, and live `/api/streamer/ocr` and OCR snapshot probes. Verified 2026-07-10.

## Security Model

- **LAN only** — designed for trusted local networks
- **TLS verification disabled** — device ships with self-signed certificate; `verify=False` in httpx client
- **No credentials in repo** — secrets are never committed, logged, or stored in files. The Comet admin password is fetched at connect time from Doppler CLI as `GLCOMET_ADMIN_PASSWORD` (`doppler.yaml` → `secrets_managment`/`dev`). Process-env injection is not used for that secret.
- **stdio exposure warning** — do not expose the MCP server's stdio to a remote agent without confirming the target host is on a trusted network
- **Remote access options:** Tailscale (native integration on Comet Pro), GL.iNet cloud service (`glkvm.com`), or VPN

### Credentials and environment

`kvm_connect` without an explicit `password` always calls the Doppler CLI. The blocker is: Doppler installed + authenticated to the project/config in `doppler.yaml`. Optional non-secret overrides:

| Variable | Secret? | Required | Default | Description |
|---|---|---|---|---|
| `COMET_HOST` | no | no | `192.168.0.126` | LAN IP of the Comet (live tests / scripts) |
| `COMET_USERNAME` | no | no | `admin` | Comet login username |
| `COMET_DISABLE_BIOS_SIDECAR` | no | no | unset | Set to `1` to skip loading `bios_sidecar` |
| `VLM_API_KEY` | **yes** | for VLM | — | OpenAI-compatible API key |
| `VLM_PROVIDER` | no | no | `mock` | `openrouter` \| `ollama` \| `vllm` \| `openai` \| `mock` |
| `VLM_MODEL` | no | no | provider default | Model string for the OpenAI-compatible endpoint |
| `VLM_BASE_URL` | no | no | provider default | Override API endpoint |

Doppler secret name: **`GLCOMET_ADMIN_PASSWORD`** (legacy alias `COMET_PASSWORD` only if you add it later).

#### MCP Client Config Example

```json
{
  "mcpServers": {
    "comet-kvm": {
      "command": "uv",
      "args": ["run", "--locked", "--python", "3.13", "python", "./glkvm_mcp.py"]
    }
  }
}
```

The host must have Doppler CLI logged in (`doppler login`). The bundled [`.mcp.json`](../../.mcp.json) launches with `uv run --locked --python 3.13 python ./glkvm_mcp.py` and does **not** wrap the process in `doppler run` for env injection.

> **Source:** `src/kvm_core/doppler_credentials.py`, `src/kvm_core/tools.py` (`kvm_connect`), `.mcp.json`, `doppler.yaml`. Verified 2026-07-16.

## Runtime Composition Assessment

`glkvm_mcp.py` contains PEP 723 dependency metadata and imports the two registration layers. `src/kvm_core/` owns the shared FastMCP instance, Comet HTTP/WebSocket client, HID workarounds, capture, OCR, logging, runtime, and universal tools. `src/bios_sidecar/` owns BIOS state, graph, perception, trace, controller, resources, and `bios_*` tool registration.

This is one MCP process and one physical Comet session, not separate KVM and BIOS servers. The modular boundary keeps universal KVM behavior usable without introducing BIOS semantics into transport code. See `docs/decisions.md` D6.

> **Source:** `glkvm_mcp.py`, `src/kvm_core/`, and `src/bios_sidecar/`. Verified 2026-07-10.
