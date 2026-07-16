# Disposable-node live qualification runbook

> **Purpose:** Prove the corrected Comet protocol and BIOS sidecar against disposable hardware before trusting ATX, MSD, mutation, or save/reboot on a valuable node.
> **Status:** Manual lane — not part of default CI.
> **Prerequisite:** Comet reachable (LAN or Tailscale), Doppler `GLCOMET_ADMIN_PASSWORD`, ATX board installed for power tests.
> **Source baseline:** Generated handler inventory in [`docs/reference/glkvm-api/`](../reference/glkvm-api/README.md), pinned to `gl-inet/glkvm@9bd8ad11ba03d220401b0b6a4208bbfd84ed6107`. The live unit may differ; record its discovered version and capabilities.

## Safety gate

Use only a disposable Proxmox/lab node with:

- No production VMs or irreplaceable disks
- Known-good recovery ISO already on the Comet (SystemRescue or similar)
- A human at the web UI as break-glass

Do **not** run forced power-off or installer mounts against production nodes.

## Lane A — Read-only connect (safe anytime)

```bash
RUN_LIVE_COMET_SMOKE=1 doppler run -p homelab -c dev -- \
  uv run --locked --python 3.13 pytest tests/live/test_live_smoke.py -q
```

The test module skips before reading credentials or opening a socket unless
`RUN_LIVE_COMET_SMOKE=1` is explicit. The GitHub workflow is manually dispatched
and fixed to a self-hosted runner carrying both `self-hosted` and `comet-lan` labels;
it cannot silently fall back to a public hosted runner.

Or manually via MCP / curl after `kvm_connect`:

1. `kvm_connect(host=..., target="pve-lab")`
2. `comet_capabilities(refresh=true)`
3. `kvm_status` — verify the WebSocket is healthy and uses `stream=true`
4. `kvm_screenshot` / `kvm_ocr_text`
5. `comet_power_state` (read only)
6. `comet_media_state`
7. `comet_recorder_state`
8. `comet_tailscale_status`
9. `comet_metrics`
10. `kvm_disconnect`

The inherited `/api/streamer/ocr` state is discovery evidence only. GL.iNet's
product Text Recognition runs browser-side Tesseract.js, while `kvm_ocr_*` uses
host Tesseract; do not record one as qualification of another.

**Pass:** capabilities profile populated; `stream=true` keeps the streamer
alive; snapshot returns JPEG; read-only calls return their expected media type;
logout completes without error.

Retain model, installed firmware, KVMD/platform data, resolution/video presence,
legacy server-OCR state, ATX enabled/LED state, MSD capacity/free space,
recorder availability, Tailscale state/addresses, and the exact routes that
succeeded or failed. Update
[`project-endpoint-coverage.csv`](../reference/glkvm-api/project-endpoint-coverage.csv)
only from retained evidence: `handler_present` is not `discovered`, and
`discovered` is not `exercised` or physically qualified.

## Lane B — Reversible HID / media (disposable target powered on)

1. `kvm_hold_key("F2", 1500)` during POST — confirm hold lasts ~1.5s (watchdog must not cut at 250ms).
2. Upload a small test file / tiny ISO via `comet_media_upload`.
3. `comet_media_mount` → verify target sees virtual CD in UEFI boot menu.
4. `comet_media_unmount` → `comet_media_remove`.
5. Optional: `comet_recorder_start` for ~5s → `comet_recorder_stop`.
6. Optional: `comet_wol_wake` against a lab NIC that is allowed to wake.

**Pass:** long hold enters setup; media mount/unmount cycle completes; no WS stall from unconsumed events (`kvm_status` shows recent `last_pong_at`).

## Lane C — Destructive ATX / BIOS / install (disposable only)

1. Document baseline ATX LED state via `comet_power_state`.
2. Soft path: `comet_atx_click("power")` then observe screenshot transition.
3. Reset: `comet_atx_power("reset_hard", wait=true)` (alias `reset` allowed).
4. BIOS: enter setup → `bios_observe_state` → change one non-blocklisted setting → verify live selection/value (not stale graph clone).
5. `bios_save_and_reboot` — require evidence fields: modal confirm, reboot_observed, final_phase.
6. Optional rebuild: mount Proxmox automated ISO → boot virtual media → answer.toml install → verify Proxmox API → unmount.

**Pass checklist**

- [ ] ATX query-param actions succeed (not JSON-body failures)
- [ ] Intentional key hold >250ms works for BIOS entry
- [ ] Observation re-extracts selected row after ArrowDown on same page
- [ ] Save/reboot returns reboot evidence (not SYNCED solely after Enter)
- [ ] ISO upload uses raw MSD write; mount/unmount restores normal boot
- [ ] Human break-glass web UI still works throughout

## Failure handling

| Symptom | Likely cause | Action |
|---------|--------------|--------|
| ATX 4xx/empty action | Old client JSON body | Confirm branch includes query-param ATX |
| Hold released early | Watchdog unprotected | Confirm `HeldKey.watchdog_protected` path |
| WS stalls after minutes | Receiver not draining | Check `comet-receiver` task / `last_server_event_at` |
| Mutation false success | Stale live state | Confirm observe always calls VLM for live fields |
| MSD multipart / 10s timeout | Old upload path | Use `comet_media_upload` streaming write |

## Sign-off

Record date, Comet firmware (`comet_capabilities`), board model, generated-source
commit, individual endpoints exercised, observed physical effects, failure and
recovery behavior, and which lanes passed in the experiment ledger
(`scripts/run_ledger.py`) before promoting the agent to autonomous recovery on
fixed nodes. A feature is qualified only when the request contract, physical
effect, resulting state, failure behavior, recovery, retained evidence, and
repeatability have all been demonstrated.
