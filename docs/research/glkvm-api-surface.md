# GLKVM / Comet native API surface

> **Kind:** Research catalog — **API facts only**  
> **Not:** Tailscale ACL advice, Proxmox factory runbooks, agent permission policy, or repo audit remediation (see sibling research docs).  
> **Companion:** Project-facing summary in [`docs/reference/comet-api.md`](../reference/comet-api.md).  
> **Authority:** Firmware source under [`gl-inet/glkvm`](https://github.com/gl-inet/glkvm) (`kvmd/apps/kvmd/api/`). No official OpenAPI.  
> **Version pins:** None. Prefer discovery GETs on the connected unit. Public identifiers observed in research (firmware/source labels, KVMD daemon version, Redfish root) change over time — query the device.  
> **Spot-checked:** 2026-07-15 against `gl-inet/glkvm` `main` handlers (confidence noted per section).

Nginx exposes these under `/api/...` (and `/redfish/...` separately). Internal handlers register paths without the `/api` prefix (e.g. `@exposed_http("GET", "/atx")` → `GET /api/atx`).

## Confidence legend

| Mark | Meaning |
|------|---------|
| **High** | Handler read on 2026-07-15; query/body shape confirmed in source |
| **Medium** | Routes enumerated from source; params not fully traced |
| **Low** | Inventory presence only; shape inferred from PiKVM/community notes |

---

## Auth and response envelope

**Confidence: High** — `kvmd/apps/kvmd/api/auth.py`

### Login

```http
POST /api/auth/login
Content-Type: application/x-www-form-urlencoded

user=<username>&passwd=<password>&expire=<seconds|0>
```

- Success (single-step): JSON `ok`/`result` with `token`; also sets `auth_token` cookie.
- Two-step enabled: may return `two_step_required`, `two_step_token`, `expires_in` instead of a session token. Complete via `POST /api/auth/two_step_complete` (form: `two_step_token`).
- Rate limit failures may return HTTP 429 with remaining-time metadata.

### Auth check methods (any one may succeed)

Order in `check_request_auth` (after optional exe-path whitelist):

1. `X-KVMD-User` + `X-KVMD-Passwd`
2. `Token` **header** (preferred for automation)
3. `auth_token` **query** parameter (works; avoid — leaks into logs/history)
4. `auth_token` **cookie**
5. HTTP Basic
6. Unix-socket credentials (when `allow_usc`)

Also: `POST /api/auth/logout`, `GET /api/auth/check`, plus two-step admin/GUI-restricted routes and rate-limit unlock helpers.

### JSON envelope

Most native JSON routes use:

```json
{ "ok": true, "result": { } }
```

**Exceptions:** JPEG/binary snapshot and downloads; streamed NDJSON (e.g. MSD remote write progress); Redfish payloads (`wrap_result=False`).

---

## Discovery (prefer over version pins)

**Confidence: High** for routes; **Medium** for exact field schemas (vary by model/firmware).

| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/upgrade/version` | Local firmware / model metadata |
| GET | `/api/info` | Optional `fields=` (e.g. `system`, `meta`, `extras`) |
| GET | `/api/system/capability` | Hardware capability files for this unit |
| GET | `/api/hid` | HID subsystem state |
| GET | `/api/atx` | ATX LED/power state |
| GET | `/api/msd` | Mass-storage / image inventory |
| GET | `/api/streamer` | Capture/stream state |
| GET | `/api/streamer/ocr` | OCR enabled/engine/languages |
| GET | `/api/recorder` | Recorder state |
| GET | `/api/tailscale/status` | Tailscale status JSON (when present) |
| GET | `/api/tailscale/config` | Stored Tailscale config toggles |
| GET | `/api/gpio` | User GPIO state |
| GET | `/redfish/v1` | Service root (`RedfishVersion` reported here) |

Do not hardcode a “current” GLKVM/KVMD/Redfish triad in clients. Discover at connect time.

---

## HID — REST and WebSocket

**Confidence: High** — `kvmd/apps/kvmd/api/hid.py`

### REST

| Method | Path | Shape |
|--------|------|-------|
| GET | `/api/hid` | State |
| GET | `/api/hid/keymaps` | Available keymaps |
| POST | `/api/hid/print` | Raw text body; query: `limit`, `keymap`, `slow` |
| POST | `/api/hid/events/send_key` | Query: `key`; optional `state`, `finish` |
| POST | `/api/hid/events/send_shortcut` | Query: `keys` (list) |
| POST | `/api/hid/events/send_mouse_button` | Query: `button`; optional `state` |
| POST | `/api/hid/events/send_mouse_move` | Query: `to_x`, `to_y` |
| POST | `/api/hid/events/send_mouse_relative` | Query: `delta_x`, `delta_y` |
| POST | `/api/hid/events/send_mouse_wheel` | Query: `delta_x`, `delta_y` |
| POST | `/api/hid/set_params` | Query: `keyboard_output`, `mouse_output`, `jiggler` |
| POST | `/api/hid/set_jiggler_schedule` | JSON body: `periods` |
| POST | `/api/hid/set_connected` | Query: `connected` |
| POST | `/api/hid/reset` | Reset HID |

### WebSocket

`GET /api/ws` (often `?stream=false` when video is not needed on the socket).

JSON events include `key`, `mouse_button`, `mouse_move`, `mouse_relative`, `mouse_wheel`. Binary event types also exist (opcodes 1–5).

Application ping shape expected by the KVMD WS parser (both fields required):

```json
{ "event_type": "ping", "event": {} }
```

Server emits subsystem `*_state` events, `pong`, and `kickout`. Clients should drain inbound messages.

---

## Streamer / OCR / snapshot

**Confidence: High** for snapshot/OCR handlers in `streamer.py`. **Medium** for broader stream-quality controls (may live in related modules / UI paths).

| Method | Path | Shape |
|--------|------|-------|
| GET | `/api/streamer` | Stream state |
| GET | `/api/streamer/snapshot` | JPEG bytes by default. Query: `save`, `load`, `allow_offline`, `preview`, `preview_max_width`, `preview_max_height`, `preview_quality`. With `ocr=true`, returns OCR JSON instead of JPEG; crop via `ocr_left`/`ocr_top`/`ocr_right`/`ocr_bottom`, langs via `ocr_langs` |
| DELETE | `/api/streamer/snapshot` | Clear saved snapshot |
| GET | `/api/streamer/ocr` | `{ "ocr": <ocr state> }` |

---

## ATX power

**Confidence: High** — `kvmd/apps/kvmd/api/atx.py`

Uses **query parameters**, not JSON bodies.

| Method | Path | Query |
|--------|------|-------|
| GET | `/api/atx` | — (LED/power state) |
| POST | `/api/atx/power` | `action=on\|off\|off_hard\|reset_hard`; optional `wait` (bool) |
| POST | `/api/atx/click` | `button=power\|power_long\|reset`; optional `wait` |

There is **no** `action=reset` on `/atx/power` — use `reset_hard`. Soft reset-like behavior for a short press is `/atx/click?button=reset`.

Requires the ATX add-on (or equivalent GPIO wiring). Without it, calls fail even when authenticated.

---

## Mass storage (MSD) lifecycle

**Confidence: High** — `kvmd/apps/kvmd/api/msd.py`

### Upload / select / connect

1. **Write image (raw body)**  
   `POST /api/msd/write?image=<name>`  
   - Body: raw image bytes  
   - Requires valid `Content-Length`  
   - Optional query: `prefix`, `remove_incomplete`  
   - **Not** multipart form upload

2. **Or remote fetch**  
   `POST /api/msd/write_remote?url=<url>&image=<name>`  
   - Optional: `insecure`, `timeout`, `remove_incomplete`  
   - May stream NDJSON progress

3. **Select params**  
   `POST /api/msd/set_params?image=<name>&cdrom=true&rw=false` (params only if provided)

4. **Attach to target**  
   `POST /api/msd/set_connected?connected=true`

### Other MSD routes

| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/msd` | State / images |
| POST | `/api/msd/set_enabled` | Query: `enabled` |
| GET | `/api/msd/read` | Stream image; optional `compress=none\|lzma\|zstd` |
| POST | `/api/msd/remove` | Query: `image` |
| POST | `/api/msd/reset` | Reset subsystem |
| GET | `/api/msd/partition_show` | Partition inventory |
| GET | `/api/msd/partition_connect` | Connect partition (**mutating GET**) |
| GET | `/api/msd/partition_disconnect` | Disconnect (**mutating GET**) |
| GET | `/api/msd/partition_format` | Format media partition (**mutating GET**; destructive) |

---

## Wake-on-LAN

**Confidence: High** — `wol.py`

| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/wol/scan` | ARP scan → device list |
| GET | `/api/wol/list` | Saved list (`/etc/kvmd/user/wol_list.json`) |
| POST | `/api/wol/wake` | Query: `mac` |
| POST | `/api/wol/add` | Query: `mac`, optional `ip`, `name` |
| POST | `/api/wol/remove` | Query: `mac` |

---

## Redfish (narrow)

**Confidence: High** — `redfish.py`

| Method | Path | Notes |
|--------|------|-------|
| GET | `/redfish/v1` | Service root; reports `RedfishVersion` (source advertises 1.6.0 schema family) |
| GET | `/redfish/v1/Systems` | Collection with member `0` |
| GET | `/redfish/v1/Systems/0` | PowerState from ATX LEDs; Reset actions |
| PATCH | `/redfish/v1/Systems/0` | No-op 204 (boot override not implemented) |
| POST | `/redfish/v1/Systems/0/Actions/ComputerSystem.Reset` | JSON body `{ "ResetType": "..." }` |

Allowable `ResetType` values in source: `On`, `ForceOn`, `ForceOff`, `GracefulShutdown`, `ForceRestart`, `PushPowerButton`.

`SetDefaultBootOrder` is advertised in the resource Actions map but **has no handler** in this module. No full Redfish virtual media / sensors / event logs.

Use Redfish for generic power orchestration; use native `/api` for HID, MSD, streamer, overlays.

---

## Recorder and metrics

**Confidence: High** for routes

| Method | Path |
|--------|------|
| GET | `/api/recorder` |
| POST | `/api/recorder/start` |
| POST | `/api/recorder/stop` |
| GET | `/api/export/prometheus/metrics` |

---

## GPIO and Fingerbot

**Confidence: High** for routes; hardware optional

### GPIO — `ugpio.py`

| Method | Path |
|--------|------|
| GET | `/api/gpio` |
| POST | `/api/gpio/switch` |
| POST | `/api/gpio/pulse` |

### Fingerbot — `fingerbot.py`

| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/fingerbot/exist` | Presence |
| GET | `/api/fingerbot/battery` | Battery |
| GET | `/api/fingerbot/local_version` | Version |
| GET | `/api/fingerbot/click` | **Mutating GET** |
| GET | `/api/fingerbot/push` | **Mutating GET** |
| GET | `/api/fingerbot/pull` | **Mutating GET** |
| POST | `/api/fingerbot/upload` | Firmware blob |
| POST | `/api/fingerbot/upgrade` | Start upgrade |

---

## Overlay networks (API existence only)

**Confidence: High** for Tailscale routes; **Medium** for peer modules (NetBird, ZeroTier, Cloudflare, TURN, etc. — files present under `api/`).

### Tailscale — `tailscale.py`

| Method | Path |
|--------|------|
| GET | `/api/tailscale/status` |
| POST | `/api/tailscale/start` |
| POST | `/api/tailscale/stop` |
| GET | `/api/tailscale/login_url` |
| GET | `/api/tailscale/login_status` |
| POST | `/api/tailscale/logout` |
| GET | `/api/tailscale/config` |
| POST | `/api/tailscale/config` |

Config parameters observed in research/discussion include exit-node and route advertisement toggles (`exit_node`, `advertise_routes`, `accept_routes`, `accept_dns`). Treat exact semantics as **discover-and-verify** on device; ops judgment about when to enable them belongs in [`oob-proxmox-tailscale-vision.md`](oob-proxmox-tailscale-vision.md), not here.

Sibling API modules (inventory only): `netbird.py`, `zerotier.py`, `cloudflare.py`, `astrowarp.py`, `turn.py`, `repeater.py`, `ap.py`, `modem.py`, `rndis.py`.

---

## Upgrade / diagnostics

**Confidence: High** for route list — `upgrade.py`

| Method | Path | Caveat |
|--------|------|--------|
| GET | `/api/upgrade/version` | Read |
| GET | `/api/upgrade/compare` | Read |
| GET | `/api/upgrade/status` | Read |
| GET | `/api/upgrade/download` | May mutate download state |
| GET | `/api/upgrade/beta/download` | Same |
| GET | `/api/upgrade/download_info` | Read |
| GET | `/api/upgrade/download_cancel` | Cancels (**mutating GET**) |
| POST | `/api/upgrade/upload` | Upload image |
| POST | `/api/upgrade/start` | Install |
| GET | `/api/upgrade/reboot` | **Mutating GET** |
| GET | `/api/upgrade/reset_default` | Factory reset (**mutating GET**) |
| POST | `/api/upgrade/edid` | Program EDID |
| GET | `/api/upgrade/get_edid` | Read EDID |
| GET | `/api/upgrade/log` | Diagnostic bundle |

---

## System / info (selected)

**Confidence: Medium–High**

| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/info` | Core info; `fields=` filter |
| GET | `/api/system/capability` | Capability files |
| GET/POST | `/api/system/*` | Network, hostname, NTP, firewall, SSL, OTG, SSH keys, etc. — large surface; many GUI-restricted via `allowed_exe_paths` |

---

## Mutating GET caveat

Several GLKVM routes change state on GET (MSD partition connect/disconnect/format, Fingerbot click/push/pull, upgrade reboot/reset/download cancel, and others). Do not expose raw URLs to generic crawlers, prefetchers, or monitoring that follows links blindly. Wrap as named actions in any agent/MCP layer.

---

## Source map

Handlers live under:

https://github.com/gl-inet/glkvm/tree/main/kvmd/apps/kvmd/api

| Topic | File |
|-------|------|
| Auth | [`auth.py`](https://github.com/gl-inet/glkvm/blob/main/kvmd/apps/kvmd/api/auth.py) |
| HID | [`hid.py`](https://github.com/gl-inet/glkvm/blob/main/kvmd/apps/kvmd/api/hid.py) |
| Streamer/OCR | [`streamer.py`](https://github.com/gl-inet/glkvm/blob/main/kvmd/apps/kvmd/api/streamer.py) |
| ATX | [`atx.py`](https://github.com/gl-inet/glkvm/blob/main/kvmd/apps/kvmd/api/atx.py) |
| MSD | [`msd.py`](https://github.com/gl-inet/glkvm/blob/main/kvmd/apps/kvmd/api/msd.py) |
| WOL | [`wol.py`](https://github.com/gl-inet/glkvm/blob/main/kvmd/apps/kvmd/api/wol.py) |
| Redfish | [`redfish.py`](https://github.com/gl-inet/glkvm/blob/main/kvmd/apps/kvmd/api/redfish.py) |
| Recorder | [`recorder.py`](https://github.com/gl-inet/glkvm/blob/main/kvmd/apps/kvmd/api/recorder.py) |
| Metrics | [`export.py`](https://github.com/gl-inet/glkvm/blob/main/kvmd/apps/kvmd/api/export.py) |
| Tailscale | [`tailscale.py`](https://github.com/gl-inet/glkvm/blob/main/kvmd/apps/kvmd/api/tailscale.py) |
| Upgrade | [`upgrade.py`](https://github.com/gl-inet/glkvm/blob/main/kvmd/apps/kvmd/api/upgrade.py) |
| System | [`system.py`](https://github.com/gl-inet/glkvm/blob/main/kvmd/apps/kvmd/api/system.py) |
| Info | [`info.py`](https://github.com/gl-inet/glkvm/blob/main/kvmd/apps/kvmd/api/info.py) |
| GPIO | [`ugpio.py`](https://github.com/gl-inet/glkvm/blob/main/kvmd/apps/kvmd/api/ugpio.py) |
| Fingerbot | [`fingerbot.py`](https://github.com/gl-inet/glkvm/blob/main/kvmd/apps/kvmd/api/fingerbot.py) |

Related: [PiKVM API docs](https://docs.pikvm.org/api/) (ancestral contract), [GL.iNet KVM docs](https://docs.gl-inet.com/kvm/).
