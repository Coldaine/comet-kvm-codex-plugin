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
                                      Tesseract OCR
                                      (host-side, reads
                                       screenshot text)
```

The MCP server (`glkvm_mcp.py`) is a **single-file Python MCP server** using PEP 723 inline script metadata. It is launched via `uv run --script ./glkvm_mcp.py` and runs as a stdio MCP server. It maintains a persistent WebSocket connection to the Comet for low-latency input, and uses HTTP for screenshots and authentication.

> **Source:** `glkvm_mcp.py` lines 1-11 (PEP 723 metadata), line 47 (FastMCP import), and `README.md#architecture`. Verified 2026-07-07.

## API Endpoints (PiKVM-Fork)

The Comet runs a PiKVM-fork firmware. The API surface is PiKVM-compatible. This project exercises three endpoints:

### 1. Authentication: `POST /api/auth/login`

```
POST /api/auth/login
Body: { "username": "admin", "password": "<password>" }
Response: Sets `auth_token` cookie; may return `two_step_required` for 2FA
```

- Default username: `admin`
- Password is passed per-session via the `kvm_connect` MCP tool — no credentials are stored server-side
- If `auth_token` is not in cookies and `two_step_required` is true, 2FA is needed (not handled in current code)
- Token is extracted from the `auth_token` cookie and used for subsequent WebSocket and HTTP calls

> **Source:** `glkvm_mcp.py` lines 322-334. Verified 2026-07-07.

### 2. Keyboard/Mouse: `WSS /api/ws?auth_token=<token>&stream=false`

WebSocket connection for real-time input:
- `stream=false` — video stream is not carried over WebSocket; screenshots use the HTTP snapshot endpoint instead
- Keyboard events: keydown, keyup (with `finish=true` flag)
- Mouse events: button press/release, absolute move (int16 coordinates), wheel scroll
- A persistent ping loop (`_pinger_loop`) keeps the connection alive at 1-second intervals

> **Source:** `glkvm_mcp.py` lines 338-339 (URL construction), lines 199-213 (pinger loop), lines 215-260 (WS send helpers). Verified 2026-07-07.

### 3. Screenshot: `GET /api/streamer/snapshot`

```
GET /api/streamer/snapshot?preview=<bool>&width=<int>&quality=<int>
Response: JPEG image bytes
```

- Returns a JPEG frame from the HDMI capture
- Parameters control preview mode (downscaled) vs. full-resolution, max width, and JPEG quality
- Used by `kvm_screenshot`, `kvm_screenshot_to_file`, `kvm_ocr_screenshot`, and `kvm_ocr_click` tools

> **Source:** `glkvm_mcp.py` lines 608, 632, 789, 821. Verified 2026-07-07.

### Endpoints Confirmed But Not Yet Exercised

The following endpoints were probed on 2026-07-07 against the target Comet at `192.168.0.126`. All return `401 Unauthorized` when unauthenticated — confirming they exist and are active, not `404`:

| Endpoint | Response | Purpose |
|---|---|---|
| `GET /api/info` | `401` | Device metadata, firmware version, hardware info |
| `POST /api/atx/*` | `401` | ATX power control — power on/off/reset the target |
| `POST /api/msd/*` | `401` | Mass Storage Device — upload ISOs/images to `/userdata/media/` |
| `POST /api/gpio/*` | `401` | GPIO pin control for ATX board |

### ATX Power Control (`POST /api/atx/*`)

**Requires the ATX add-on board** — a separate hardware accessory that wires to the motherboard's power/reset headers. Without this board, the API will return an error even when authenticated.

The PiKVM ATX API typically supports:
- `POST /api/atx/power` with `{"action": "on"|"off"|"reset"}`
- `POST /api/atx/click` with `{"button": "power"|"reset"}` (momentary press, ~200ms)

MCP tools: `comet_atx_power`, `comet_atx_click` (in `glkvm_mcp.py`).

### Mass Storage (`POST /api/msd/*`)

The Comet's `/userdata/media` partition (~5.3GB free on the 8GB model) is the write target for MSD operations. This is where BIOS maps and state databases should be persisted per `docs/decisions.md` D4.

MCP tools: `comet_msd_upload` (in `glkvm_mcp.py`) — uploads a file to `/userdata/media/` for on-device state persistence.

### System Info (`GET /api/info`)

Returns device metadata: model, firmware version, serial, hardware capabilities. Useful for agent self-discovery.

MCP tool: `comet_sysinfo` (in `glkvm_mcp.py`).

### GPIO (`POST /api/gpio/*`)

Low-level GPIO control for the ATX board. Typically not needed directly — the ATX API wraps GPIO operations.

> **Probe date:** 2026-07-07 against `192.168.0.126`. All four endpoints returned `401` (not `404`), confirming they are active on this device.

## MCP Tools Exposed by `glkvm_mcp.py`

### Connection
| Tool | Signature | Annotations | Description |
|------|-----------|-------------|-------------|
| `kvm_connect` | `(host, password, username?)` | write, non-destructive, idempotent | Connect to Comet on LAN |
| `kvm_disconnect` | `()` | write, non-destructive, idempotent | Close session + cleanup |
| `kvm_status` | `()` | read-only, non-destructive, idempotent | Report connection state + held keys |

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
| `kvm_ocr_screenshot` | `(search_text?, preview?)` | read-only, non-destructive, idempotent | Capture + Tesseract OCR → structured JSON with text + coordinates |
| `kvm_ocr_click` | `(text, button?, count?, search_area?)` | write, destructive | OCR-find text → click it (all-in-one) |

> **Source:** `glkvm_mcp.py` — `@mcp.tool` decorators with annotations at lines 293, 361, 400, 436, 478, 504, 520, 537, 548, 568, 584, 613, 751, 794, 884. Verified 2026-07-07.

## Internal Background Tasks (Asyncio)

`glkvm_mcp.py` already runs **two background asyncio loops** within the single MCP server process. This is the existing pattern that the proposed state engine would follow as a third loop:

### `_watchdog_loop` (40ms period)
- Monitors held keys
- Force-releases any key still tracked as held after `STALE_S` (250ms)
- Prevents stuck keys from input sequences that were interrupted or failed

### `_pinger_loop` (1s period)
- Sends WebSocket ping frames to keep the connection alive
- Detects dropped connections

> **Source:** `glkvm_mcp.py` lines 180-197 (watchdog), lines 199-213 (pinger). Verified 2026-07-07.

**Design implication:** A state-engine screen-poller would join these as a third background loop (e.g. `_screen_poll_loop`). This is the existing architectural pattern, not a new one. The MCP server already holds session state (the `Connection` dataclass at line 159) and runs background tasks — it is not, and has never been, purely stateless in the process sense. The "stateless transport" framing refers to the API contract (no tool call depends on prior tool-call state), not the process internals. See `docs/decisions.md` D7.

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
> - `glkvm_mcp.py` docstring lines 18-26, tunables lines 52-56. Verified 2026-07-07.
> - `README.md#firmware-bug-fixes`. Verified 2026-07-07.

## OCR Integration (Tesseract)

OCR runs **on the host**, not on the Comet:

- Tesseract binary is located via `TESSERACT_PATH`/`TESSERACT_CMD` env vars, then `PATH`, then Windows default paths
- `kvm_ocr_screenshot` captures a frame, passes it to Tesseract, and returns structured JSON:
  ```json
  {
    "width": 1920,
    "height": 1080,
    "elements": [
      {"text": "File", "confidence": 96.3, "x_pct": 5.2, "y_pct": 3.1},
      {"text": "Edit", "confidence": 95.8, "x_pct": 8.7, "y_pct": 3.1}
    ]
  }
  ```
- `kvm_ocr_click` finds text by name and clicks its exact coordinates — eliminates the "vision model estimates pixel position" unreliability

> **Source:** `glkvm_mcp.py` lines 650-674 (Tesseract binary lookup), lines 686-749 (OCR implementation), and `README.md#mcp-tools`. Verified 2026-07-07.

## Security Model

- **LAN only** — designed for trusted local networks
- **TLS verification disabled** — device ships with self-signed certificate; `verify=False` in httpx client
- **No credentials in repo** — secrets are never committed, logged, or stored in files. They are injected as environment variables at process start, typically through the MCP client config `env` dict.
- **stdio exposure warning** — do not expose the MCP server's stdio to a remote agent without confirming the target host is on a trusted network
- **Remote access options:** Tailscale (native integration on Comet Pro), GL.iNet cloud service (`glkvm.com`), or VPN

### Environment Variables

The server reads these from its environment. They can be injected via shell export, `.env`, MCP client config (`env` in `StdioTransport`), or Doppler.

| Variable | Secret? | Required | Default | Description |
|---|---|---|---|---|
| `COMET_PASSWORD` | **yes** | yes | — | Comet KVM admin password |
| `COMET_HOST` | no | no | `192.168.0.126` | LAN IP of the Comet |
| `COMET_USERNAME` | no | no | `admin` | Comet login username |
| `VLM_API_KEY` | **yes** | for VLM | — | OpenAI-compatible API key (OpenRouter, OpenAI, or set to any value for local Ollama) |
| `VLM_PROVIDER` | no | no | `mock` | `openrouter` \| `ollama` \| `vllm` \| `openai` \| `mock` |
| `VLM_MODEL` | no | no | provider default | Model string routed by litellm (e.g. `openrouter/qwen/qwen-2-vl-72b-instruct`) |
| `VLM_BASE_URL` | no | no | provider default | Override API endpoint (e.g. `http://localhost:11434/v1` for Ollama) |

#### MCP Client Config Example

```json
{
  "mcpServers": {
    "comet-kvm": {
      "command": "uv",
      "args": ["run", "glkvm_mcp.py"],
      "env": {
        "COMET_PASSWORD": "your-password-here",
        "COMET_HOST": "192.168.0.126",
        "VLM_API_KEY": "sk-or-...",
        "VLM_PROVIDER": "openrouter"
      }
    }
  }
}
```

For local development with Doppler: `doppler run -- uv run glkvm_mcp.py`.

> **Source:** `glkvm_mcp.py` docstring lines 27-29 and `README.md#security`. Verified 2026-07-07.

## Single-File Architecture Assessment

`glkvm_mcp.py` is a **single-file MCP server** that contains:

- PEP 723 inline dependency metadata (no separate `requirements.txt` or `pyproject.toml` needed for the server itself)
- The `FastMCP` server definition and all 15 tool functions
- The `Connection` dataclass (session state: base_url, httpx client, WebSocket)
- Two background asyncio loops (watchdog, pinger)
- Tesseract OCR integration
- Key/mouse input protocol implementation with bug workarounds

**Current state:** This is a collapsed single-file MCP server — transport, session management, OCR, and bug workarounds all in one file. It works for the bootstrap scope (connect, screenshot, OCR, input, release).

**Growth pressure:** Adding a state engine (3rd asyncio loop + screen-polling + map-matching) and potentially crawler-driving hooks will push this file past the point where a single file remains maintainable. The file structure is not a hard constraint — if it splits, it would separate transport (Comet API client) from state (session, polling, map-matching) from OCR (Tesseract integration) into modules within the same package, not into separate MCP servers. See `docs/decisions.md` D6.

> **Source:** `glkvm_mcp.py` full file. Verified 2026-07-07.
