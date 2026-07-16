# Comet KVM API & Software Surface Reference

> **Repo:** `Coldaine/comet-kvm-codex-plugin` (fork of `kennypeh85/glkvm-mcp`)
> **Status:** Project-facing summary of upstream contracts this MCP cares about, plus what tools this repo exposes. Fuller endpoint inventory: [`docs/research/glkvm-api-surface.md`](../research/glkvm-api-surface.md).
> **Compiled:** 2026-07-07 · **Revised:** 2026-07-15 (auth/discovery/ATX/MSD/verification)
> **Purpose:** Auth, discovery, important request shapes, live-probe status, and MCP tool tables. Not ops advice (see [`docs/research/oob-proxmox-tailscale-vision.md`](../research/oob-proxmox-tailscale-vision.md)). Not a client-bug tracker (see [`docs/research/glkvm-client-audit-2026-07-15.md`](../research/glkvm-client-audit-2026-07-15.md)).

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

> **Source:** `glkvm_mcp.py`, `src/kvm_core/server.py`, `src/kvm_core/runtime.py`. Verified 2026-07-10.

**Versioning note:** There is no single native “API version.” Prefer connect-time discovery (`/api/upgrade/version`, `/api/info`, `/api/system/capability`, subsystem GETs) over pinning firmware/KVMD/Redfish triples in clients. There is no official OpenAPI for `/api`; [gl-inet/glkvm](https://github.com/gl-inet/glkvm) handlers are the contract. See the [research catalog](../research/glkvm-api-surface.md).

**JSON envelope:** Most native JSON routes return `{ "ok": true, "result": { ... } }`. Exceptions: JPEG/binary downloads, NDJSON progress streams, and Redfish (`wrap_result=False`).

## Upstream contracts (firmware)

The Comet runs a PiKVM-fork firmware. Paths below are the public `/api/...` forms.

### Authentication

```
POST /api/auth/login
Form body: user=admin&passwd=<password>&expire=0
```

- Default username: `admin`
- Password is passed per-session via `kvm_connect`, or fetched from Doppler CLI (`GLCOMET_ADMIN_PASSWORD` per `doppler.yaml`; legacy alias `COMET_PASSWORD` if present) — never from process environment, never stored server-side
- Success returns `result.token` and sets `auth_token` cookie; may return `two_step_required` / `two_step_token` when two-step login is enabled
- Firmware accepts (among others): **`Token` header** (preferred), `auth_token` cookie, HTTP Basic, `X-KVMD-User` / `X-KVMD-Passwd`, `auth_token` query (avoid — leaks into logs)
- This repo's client stores the cookie token and sends the HTTP `Token` header on subsequent requests; WebSocket auth uses `Cookie: auth_token=...` and `Token` headers (not a query-string token)
- Clean disconnect calls `POST /api/auth/logout`; also `GET /api/auth/check`

> **Source:** `gl-inet/glkvm` `kvmd/apps/kvmd/api/auth.py` (spot-checked 2026-07-15); `src/kvm_core/comet/client.py` (`CometClient.connect` / `disconnect`). Confidence: **High**.

### Discovery

Useful GETs before assuming features:

| Path | Role |
|------|------|
| `GET /api/upgrade/version` | Firmware / model reporting |
| `GET /api/info` (optional `fields=`) | System / meta / extras |
| `GET /api/system/capability` | Model capability files |
| `GET /api/hid`, `/api/atx`, `/api/msd`, `/api/streamer`, `/api/streamer/ocr`, `/api/recorder` | Subsystem state |
| `GET /api/tailscale/status`, `/api/tailscale/config` | Overlay status when present |

MCP today exposes `GET /api/info` via `comet_sysinfo` / `comet_capabilities`. Connect-time discovery also probes `/api/upgrade/version`, `/api/system/capability`, and subsystem GETs. Fuller route inventory remains in the research catalog.

### Keyboard/Mouse WebSocket: `WSS /api/ws`

- Typical query: `stream=false` (video via HTTP snapshot, not WS)
- Auth: cookie / `Token` header; query `auth_token` also accepted by firmware (prefer header/cookie — this client uses header/cookie)
- Keyboard events: keydown, keyup (with `finish=true` flag)
- Mouse events: button press/release, absolute move (int16 coordinates), wheel scroll
- Application ping must include **both** fields: `{"event_type":"ping","event":{}}`
- A receiver task drains server events (`*_state`, `pong`, `kickout`) and caches the latest subsystem state
- Intentional `kvm_hold_key` holds are watchdog-protected until their release deadline

> **Source:** PiKVM handbook + GLKVM WS handling; `src/kvm_core/comet/client.py`; research catalog. Confidence: **Medium–High**.

### Screenshot / OCR

```
GET /api/streamer/snapshot?preview=<bool>&preview_max_width=<int>&preview_quality=<int>
→ JPEG bytes

GET /api/streamer/ocr
→ native OCR capability

GET /api/streamer/snapshot?ocr=true&ocr_langs=...&ocr_left=...&ocr_top=...&ocr_right=...&ocr_bottom=...
→ OCR JSON when enabled
```

Used by `kvm_screenshot`, `kvm_screenshot_to_file`, `kvm_ocr_*` tools. Live unit at `192.168.0.126` (2026-07-10): OCR capability endpoint HTTP 200 with `enabled: false`; OCR snapshot returned HTTP 500 while disabled → host Tesseract fallback.

> **Source:** GLKVM `streamer.py`, `src/kvm_core/comet/client.py`, live probes 2026-07-10. Confidence: **High**.

### ATX power control

**Requires the ATX add-on board.** Without it, calls fail even when authenticated.

Firmware uses **query parameters**, not JSON bodies (**High** confidence — `kvmd/apps/kvmd/api/atx.py`):

| Method | Path | Query |
|--------|------|-------|
| GET | `/api/atx` | — state / LEDs |
| POST | `/api/atx/power` | `action=on\|off\|off_hard\|reset_hard`, optional `wait=true\|false` |
| POST | `/api/atx/click` | `button=power\|power_long\|reset`, optional `wait` |

There is no `action=reset` on `/atx/power` — use `reset_hard`.

```
POST /api/atx/power?action=reset_hard&wait=true
POST /api/atx/click?button=power_long&wait=true
```

MCP aliases: `reset` → `reset_hard`, `force_off` → `off_hard`.

MCP tools: `comet_power_state`, `comet_atx_power`, `comet_atx_click` (see tool table). Treat this section as the **firmware** contract; historical client/doc mismatches are recorded in the [2026-07-15 audit snapshot](../research/glkvm-client-audit-2026-07-15.md).

### Mass storage (MSD)

Virtual media lifecycle (**High** confidence — `msd.py`):

1. `POST /api/msd/write?image=<name>` — **raw image body** + `Content-Length` (not multipart)
2. Optional: `POST /api/msd/write_remote?url=...&image=...` — Comet downloads (may stream NDJSON progress)
3. `POST /api/msd/set_params?image=...&cdrom=true&rw=false`
4. `POST /api/msd/set_connected?connected=true|false`
5. `GET /api/msd` — state / images / storage

Also: `remove`, `reset`, partition show/connect/disconnect/format (some are **mutating GETs** — do not prefetch).

MCP tools: `comet_media_state`, `comet_media_upload`, `comet_media_fetch`, `comet_media_mount`, `comet_media_unmount`, `comet_media_remove`, `comet_media_reset` (plus legacy `comet_msd_upload`). Catalog has the complete upstream route list.

### System info

`GET /api/info` — device metadata. Connect-time discovery also probes `/api/upgrade/version`, `/api/system/capability`, and subsystem GETs.

MCP tools: `comet_sysinfo`, `comet_capabilities`.

### GPIO

`GET/POST /api/gpio/*` — low-level GPIO; ATX API usually preferred. No dedicated MCP tool.

### Broader surface

WOL, Redfish (narrow power facade), recorder, Prometheus export, Tailscale config/status, Fingerbot, upgrade/diagnostics — inventoried in [`docs/research/glkvm-api-surface.md`](../research/glkvm-api-surface.md). Not all are wrapped by this MCP.

## Verification status

What this project has actually exercised against the LAN Comet (`192.168.0.126`). Destructive ATX actions and MSD uploads were **not** invoked in read-only probes.

| Surface | Live tested? | When / notes |
|---------|--------------|--------------|
| `POST /api/auth/login` | Yes | Authenticated sessions 2026-07-07 / 2026-07-10 |
| `GET /api/info` | Yes | HTTP 200 authenticated 2026-07-10 |
| `GET /api/streamer/snapshot` | Yes | JPEG capture via MCP tools |
| `GET /api/streamer/ocr` | Yes | HTTP 200; `enabled: false` on unit 2026-07-10 |
| Snapshot OCR (`ocr=true`) | Partial | HTTP 500 while OCR disabled; host Tesseract used |
| WebSocket HID (keys/mouse) | Yes | Primary input path in normal MCP use |
| `GET /api/atx` | Existence only | Not action-tested |
| `POST /api/atx/power` / `click` | **Not live-tested** | No destructive power tests in smoke |
| `POST /api/msd/write` + mount lifecycle | **Not live-tested** | Upload not invoked in 2026-07-10 verification |
| WOL / Redfish / Tailscale / recorder / metrics | **Not live-tested** | Documented from source inventory only |
| Offline CI | Yes | stdio MCP list-tools smoke, mocked protocol tests (see CI) |

Manual live smoke: `.github/workflows/live-smoke.yml` (Doppler + runner with Comet reachability). Preflight without KVM actions: `scripts/comet_preflight.py`.

## This repo’s MCP tools

This section is **this repo’s tool surface**, not the full firmware catalog. Keep it separate from the upstream-contract sections above.

### Connection
| Tool | Signature | Annotations | Description |
|------|-----------|-------------|-------------|
| `kvm_connect` | `(host, password?, username?, target?)` | write, non-destructive, idempotent | Connect to Comet on LAN; omitted password is fetched from Doppler CLI (`GLCOMET_ADMIN_PASSWORD`); optional `target` enables multi-Comet sessions |
| `kvm_disconnect` | `(target?)` | write, non-destructive, idempotent | Close one target or all sessions + cleanup |
| `kvm_select_target` | `(target)` | write, non-destructive, idempotent | Select the active multi-Comet target for subsequent tools |
| `kvm_status` | `()` | read-only, non-destructive, idempotent | Report connection state + held keys + target list |

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
| `comet_wol_*` | — | — | list/scan (`GET`) / wake (`POST /api/wol/wake`) |
| `comet_streamer_*` / `comet_recorder_*` | — | — | stream + recording controls |
| `comet_metrics` | `(target?)` | read-only | Prometheus metrics text |
| `comet_tailscale_status` | `(target?)` | read-only | Tailscale status |
| `comet_redfish_power` | `(reset_type, target?)` | write, destructive | Redfish ComputerSystem.Reset |

This table is **MCP tool names only**. Full upstream routes stay in the [research catalog](../research/glkvm-api-surface.md). Historical client mismatches (if any) are snapshotted in the [2026-07-15 audit](../research/glkvm-client-audit-2026-07-15.md) — do not treat audit blockers as current API facts.

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

| Source | What it covers |
|--------|----------------|
| [docs/research/README.md](../research/README.md) | Research index + homes map |
| [docs/research/glkvm-api-surface.md](../research/glkvm-api-surface.md) | Fuller endpoint inventory, auth detail, source links |
| [docs/research/oob-proxmox-tailscale-vision.md](../research/oob-proxmox-tailscale-vision.md) | Ops vision (judgment; not API facts) |
| [docs/research/glkvm-client-audit-2026-07-15.md](../research/glkvm-client-audit-2026-07-15.md) | Dated client-vs-firmware audit snapshot |
| [PiKVM API docs](https://docs.pikvm.org/api/) | Canonical PiKVM HTTP/WebSocket API (Comet firmware is a fork) |
| [GL.iNet KVM docs](https://docs.gl-inet.com/kvm/) | Comet product documentation and user guides |
| [gl-inet/glkvm](https://github.com/gl-inet/glkvm) | Firmware source; API handlers under `kvmd/apps/kvmd/api/` |
| [kennypeh85/glkvm-mcp](https://github.com/kennypeh85/glkvm-mcp) | Upstream MCP server this repo forked from |

## Internal Background Tasks (Asyncio)

The MCP process runs **two background asyncio loops** for transport reliability:

### `_watchdog_loop` (40ms period)
- Monitors held keys
- Force-releases any key still tracked as held after `STALE_S` (250ms)
- Prevents stuck keys from input sequences that were interrupted or failed

### `_pinger_loop` (1s period)
- Sends WebSocket application pings to keep the connection alive
- Detects dropped connections

> **Source:** `src/kvm_core/comet/client.py` (`_watchdog_loop` and `_pinger_loop`). Verified 2026-07-10.

**Design implication:** These loops are transport reliability mechanisms. The BIOS state tracker remains on demand; it is not an always-on third screenshot/OCR loop. A future bounded terminal observer should poll only for the duration of its active tool call. See `docs/decisions.md` D7 and D-K7.

## Known Firmware Bugs & Workarounds

### Stuck Key / Double-Typing (Firmware ≤ 1.9.0)
- **Bug:** Characters sent rapidly can double-type or get stuck in the down state
- **Fix in client:** Every character is sent as an atomic `keydown → 25ms → keyup(finish=true)` pattern
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
- `kvm_ocr_screenshot` captures a frame, passes it to Tesseract, and returns structured JSON with word coordinates
- `kvm_ocr_click` finds text by name and clicks its exact coordinates
- Pillow supplies decoded image dimensions; pytesseract is bounded to 15 seconds and runs off the MCP asyncio loop

### Device-side OCR capability

GL.iNet's PiKVM fork exposes `GET /api/streamer/ocr` with `enabled`, `engine` (`tesseract` or `rknn`), and language state. On 2026-07-10, the live Comet at `192.168.0.126` returned `enabled: false`, engine `tesseract`, and no available/default languages; the native snapshot call returned HTTP 500, so host Tesseract is selected on that unit. Native OCR does not replace host word boxes used for coordinate-sensitive tools.

> **Source:** `src/kvm_core/ocr.py`, `src/kvm_core/tools.py`, and live probes. Verified 2026-07-10.

## Security Model

- **LAN only** — designed for trusted local networks
- **TLS verification disabled** — device ships with self-signed certificate; `verify=False` in httpx client
- **No credentials in repo** — secrets are never committed, logged, or stored in files. The Comet admin password is fetched at connect time from Doppler CLI as `GLCOMET_ADMIN_PASSWORD` (`doppler.yaml` → `secrets_managment`/`dev`). Process-env injection is not used for that secret.
- **stdio exposure warning** — do not expose the MCP server's stdio to a remote agent without confirming the target host is on a trusted network
- **Remote access options:** Tailscale (supported on Comet models that ship the integration), GL.iNet cloud service (`glkvm.com`), or VPN — topology judgment is **not** documented here; see the [OOB vision](../research/oob-proxmox-tailscale-vision.md) if needed

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
