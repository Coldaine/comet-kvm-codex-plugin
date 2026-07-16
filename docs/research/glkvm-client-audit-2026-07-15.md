# GLKVM client audit snapshot — 2026-07-15

> **Kind:** Dated **research snapshot** of a source-level repo-vs-firmware review.  
> **Not** an implementation plan, protocol-correction PR, or API reference.  
> **Homes for follow-up:** Protocol/contract facts → [`glkvm-api-surface.md`](glkvm-api-surface.md) / [`docs/reference/comet-api.md`](../reference/comet-api.md). Ops judgment → [`oob-proxmox-tailscale-vision.md`](oob-proxmox-tailscale-vision.md).  
> **Scope of this pass:** Capture findings so they are not lost. **No code fixes here.**

**Method:** Source review against public GLKVM handlers and this repository’s `main` tree as of the audit date. **No live destructive commands** were sent to hardware as part of the audit writeup.

**Deployment caution from the audit:** Prefer screenshot, OCR, and ordinary keyboard/mouse primitives. Do not trust ATX, MSD, BIOS mutation, or save-and-reboot paths on a valuable node until protocol/BIOS correctness work lands.

---

## What the repository gets right (per audit)

- Decomposition: MCP tools → `kvm_core` (HTTP auth, WebSocket HID, screenshots, OCR) + `bios_sidecar` (state graph, observation, navigation, mutation).  
- Shared runtime avoids a second independent Comet session; sidecar depends on kvm_core (one-way).  
- Screenshot path uses `/api/streamer/snapshot` with preview/offline parameters.  
- Native OCR + host Tesseract fallback wiring is substantially correct.  
- JSON keyboard/mouse WebSocket messages generally follow KVMD event schema.  
- `kvm_screenshot_to_file` containment to screenshot cache is sound.  
- Core/BIOS separation is better than a monolith.

---

## Blockers claimed (transport)

### B1 — ATX wrong request shape and action name

- **Repo (as audited):** `CometClient.atx_power` / `atx_click` POST JSON bodies (`{"action": "reset"}`, etc.); actions include `reset` not `reset_hard`.  
- **Firmware:** Query params — `POST /api/atx/power?action=on|off|off_hard|reset_hard&wait=...`, `POST /api/atx/click?button=power|power_long|reset&wait=...`, plus `GET /api/atx`.  
- **Doc debt:** `docs/reference/comet-api.md` (pre-correction) described JSON-body ATX — must stay aligned with firmware after any client fix.  
- **Homes:** Facts in API research/reference; remediation is a future protocol PR (out of this docs pass).

### B2 — MSD upload wrong protocol

- **Repo:** Multipart form with path field + file; may prepend `userdata/media/`; loads whole file into memory; short HTTP timeout unsuitable for multi-GB ISOs.  
- **Firmware:** `POST /api/msd/write?image=<name>` with **raw body** + `Content-Length`; then `set_params` + `set_connected`. Optional `write_remote` with NDJSON progress.  
- **Homes:** Lifecycle documented in API research; tool split (`comet_media_*`) is a future ops/API expansion, not this snapshot’s job.

### B3 — WebSocket keepalive malformed; no receive task

- **Repo:** Sends `{"event_type": "ping"}` without required `event` object; send-side pinger only; does not consume server `*_state` / `pong` / `kickout`.  
- **Risk:** Inbound queue fill → unreliable session.  
- **Homes:** Correct ping shape in API research; receiver/reconnect tasks are future client work.

### B4 — `kvm_hold_key` defeated by 250 ms watchdog

- Holds up to 5000 ms requested; watchdog force-releases keys held > ~250 ms (`stale_s = 0.250`).  
- Breaks BIOS-entry holds (Delete/F2) during POST.  
- Needs intentional vs accidental hold tracking (watchdog-protected deadlines).

### B5 — Auth / session modernization gaps

- Cookie from login; WebSocket `auth_token` in **query string**; no Token-header preference; no logout on disconnect; global TLS verify disable; two-step login not handled as a defined flow.  
- Firmware accepts Token header, Basic, X-KVMD-*, cookie, query token, USC.

---

## Blockers claimed (BIOS / perception)

### B6 — Observation reuses stale live interaction state

- Matching a known screen clones prior `BiosState` and replaces frame/run/confidence metadata without re-extracting selected row, value, options, modal, control positions.  
- Coarse 9×8 dhash can miss cursor/value/modal changes → false mutation verify success/failure.  
- Needed split: **ScreenIdentity** vs **LiveInteractionState**.

### B7 — `bios_save_and_reboot` under-verifies

- F10 → weak modal/title heuristics → Enter → returns pre-confirmation state; marks SYNCED without observing reboot/POST.  
- Needs explicit confirmation extraction, REBOOTING runtime phase, evidence in result.

### B8 — Crawler not near-exhaustive

- Frontier mostly Enter (submenu) + ArrowDown; visiting same coarse page node treated as cycle → ArrowDown can abort enumeration.  
- Needs page node vs cursor state; enumerate controls within a page; hard operational limits (`max_actions`, wall clock, unknown screens, etc.).

### B9 — `kvm_vlm_parse` screenshot path escape

- Joining caller path with cache via `os.path.join` can discard cache prefix on absolute paths / allow `..` traversal → local file read sent to VLM.  
- Fix direction: opaque screenshot IDs + resolve containment (same pattern as screenshot output paths).

---

## Underused API / product gaps (audit list)

Only a small Comet hardware tool set exposed (`comet_atx_power`, `comet_atx_click`, `comet_sysinfo`, `comet_msd_upload`) vs firmware surface (WOL, recorder, metrics, Tailscale, Redfish, full MSD lifecycle, capability discovery, etc.).

Connect-time discovery should probe version/info/capability + subsystem GETs and return a feature profile — `comet_sysinfo` → `/api/info` alone is insufficient.

Multi-Comet: process-global singleton disconnects prior host; audit recommends target registry (see ops vision open questions).

---

## Test-lane gaps claimed

| Lane | Claim |
|------|-------|
| Offline protocol-contract | Smoke tests mostly register tools; do not assert ATX query params / MSD raw body / WS ping shape. Pending tests may encode wrong ping. |
| Read-only live | Login, info, screenshot — cannot detect ATX/MSD bugs. |
| Reversible hardware | Missing structured lane (harmless key, tiny media, mount/unmount, WOL, short record). |
| Destructive / disposable | Should be explicit CI against designated hardware, not ad-hoc agent approval theater. |

---

## Recommended implementation order (from audit — not executed here)

1. **Protocol-correction PR** — ATX query params + aliases; MSD raw stream + mount lifecycle; WS ping + receiver; hold_key; logout; contract tests.  
2. **BIOS correctness PR** — identity vs live state; save/reboot evidence; crawler model; VLM path containment.  
3. **Complete Comet operations PR** — discovery, media, WOL, stream, recorder, metrics, Tailscale status, multi-target.  
4. **Live hardware qualification** — disposable node proof path.

---

## Surface assessment table (audit verdict)

| Surface | Assessment |
|---------|------------|
| Screenshots | Usable |
| Native OCR + Tesseract fallback | Usable |
| Ordinary keyboard/mouse | Mostly usable |
| Long key holds | Broken above ~250 ms |
| WebSocket session reliability | Incomplete |
| ATX API | Incorrectly implemented |
| MSD upload | Incorrectly implemented |
| Virtual-media provisioning | Largely absent |
| BIOS screen identity | Promising but coarse |
| BIOS dynamic-state verification | Unsafe/stale |
| BIOS crawl exhaustiveness | Not achieved |
| Save-and-reboot verification | Insufficient |
| Multi-Comet | Absent |
| Tailnet administration | Not exposed |
| Automated destructive ops | Not yet trustworthy |

---

## Verification note for this snapshot file

Spot-check of `src/kvm_core/comet/client.py` on the docs branch base (`main` as of worktree creation) still showed JSON-body ATX, multipart MSD, ping without `event`, query-string WS token, and `stale_s = 0.250` — consistent with the paste’s transport blockers. BIOS/VLM findings were not re-proven line-by-line in this docs pass; treat B6–B9 as **audit claims** pending a dedicated verification PR.

**No protocol-correction or BIOS fixes are made in this documentation pass.**
