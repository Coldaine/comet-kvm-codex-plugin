# Implementation Decisions

> **Repo:** `Coldaine/comet-kvm-codex-plugin` (fork of `kennypeh85/glkvm-mcp`)
> **Authority:** #2 in the [Authority Order](NORTH_STAR.md#authority-order). These are decisions about *how* we build the thing, not *what* the thing is (that's NORTH_STAR.md) or *how to behave* in the repo (that's AGENTS.md). See `docs/architecture.md` for the full justification of each decision.

## D1 — Screenshot retention: TTL, not permanent

Runtime screenshots are persisted temporarily for retry, debugging, and map-building, then automatically purged after approximately 30 days. They are never committed to Git. The retention is a cleanup policy, not a git policy — the TTL runs against whatever runtime data directory the installed plugin uses (host-side or on-Comet).


## D3 — Cartography skill placement: reference under active plans

BIOS cartography is a specialized subset of the `comet-bios-triage` skill, not a sibling skill. It is documented under `docs/architecture.md` and active plans (e.g. `docs/plans/01-vlm-mcp-integration-plan.md`). The existing skill's trigger surface already covers BIOS workflows; cartography is a prerequisite step within that workflow, not a separate capability.

## D4 — Map store runtime location: on-Comet preferred, pending verification

BIOS maps should persist on the Comet device itself, co-located with the hardware they describe. The Comet (GL-RM1) has 8GB eMMC with ~5.3GB free at `/userdata/media`, confirmed via root shell evidence in gl-inet/glkvm#14. A BIOS map is ~30-40MB, so the device has two orders of magnitude more storage than needed.

**Probe result (2026-07-07):** The Comet at `192.168.0.126` is reachable via HTTP (200 OK, PiKVM-fork nginx) and SSH (port 22 open, accepts publickey+password auth). However, SSH credentials are needed to verify `/userdata/media` writability and free space on this specific device. The device is architecturally suitable but storage writability is **unverified without credentials**.

**Fallback:** If on-Comet storage proves impractical, maps persist in the host-side plugin data directory. The VLM interpretation layer always runs on the host (the Comet has no GPU) regardless of where maps are stored.

## D5 — Fuzzy matching against similar boards: not a goal

Fuzzy matching is not a core requirement. The driver agent can look at stored maps and then decide if a map is similar enough to be imported and reused. We prioritize agent-led comparison over automated heuristic matching.

## D6 — glkvm_mcp.py file structure: not a hard constraint

`glkvm_mcp.py` is currently a single-file MCP server. It already runs two background asyncio loops (watchdog + pinger) and holds session state. The planned state engine will join as a third background loop in the same file. This is not a hard constraint — if the file's complexity grows past the point where a single file is maintainable (e.g. after adding the state engine and crawler-driving hooks), it may be split into modules within the same package. That split, if it comes, separates transport (Comet API client) from state (session, polling, map-matching) from OCR (Tesseract integration) — not into separate MCP servers.

## D7 — State engine deployment: internal asyncio tracking

The stateful screen-level position tracker runs inside the MCP server process, keeping track of which graph node the session is currently on. Instead of running a background loop that constantly polls (which is slow and expensive), the state tracker is updated on-demand when the Driver Agent calls tools like `bios_observe_state`, `bios_navigate_to`, or `bios_apply_setting_change`. The MCP server matches screens locally using perceptual hashes and OCR fingerprints (`kvm_match_screen`), calling the VLM tool (`kvm_vlm_parse`) only when grounding is needed.

## D8 — Two granularity levels: workflow phases vs screen position

**Status: QUESTIONED.** User does not understand this concept yet; do not enshrine the workflow phase ledger as product architecture without re-evaluation.

The project operates at two distinct granularity levels that complement, not replace, each other:

- **Workflow level** (`stateful-control-model.md`): phases like `planned → preflight → bios-entry → bios-edit → save-confirm → windows-boot → hwinfo-log → analysis → done`. Agent-maintained, persisted in the run ledger. Asks "are we in the edit phase?"
- **Screen level** (state engine): which BIOS menu node are we on right now, matched against a stored map. Background-maintained, ephemeral per session. Asks "are we on the Overclocking submenu row 3, and did that Enter press land where the map predicted?"

## D9 — Output format: Semantic Capability Index + screen-node graph

The crawler produces two views of the same crawl data:

- **Semantic Capability Index** (for the driver agent): a JSON file keyed by setting name, containing the navigation path, UI type, available options, and interaction keys. The driver reads this to navigate deterministically without calling the VLM.
- **Screen-node graph** (for the state engine): a network of screen nodes keyed by perceptual hash + OCR fingerprint, with edges labeled by the keystroke that transitions between them. The state engine matches live screenshots against these nodes for transition validation.

The crawler produces the graph (raw crawl data). A post-processing step derives the index from the graph. Both are persisted. See `docs/architecture.md` §9 for the full rationale.

## D10 — REMOVED: VLM framework choice as product architecture

Removed as a durable decision. VLM implementation details may still exist inside the BIOS sidecar, but they are sidecar-internal and do not define the KVM MCP core product.

## D11 — REMOVED: Approval/policy-gated authority model

Removed as product architecture. Approval tokens, `bios_grant_human_approval`, and policy-gated authority are cut from the docs. Tool annotations, path safety, stale-key watchdog behavior, destructive labeling, and visual verification remain. `bios_save_and_reboot` checking that a save dialog is visible before pressing Enter is screen-state verification, not approval-token policy.

## D-K1 — KVM tool surface plus deprecated aliases

The KVM core exposes these unique driver-facing tools: `kvm_connect`, `kvm_disconnect`, `kvm_status`, `kvm_send_text`, `kvm_send_keys`, `kvm_hold_key`, `kvm_release_all`, `kvm_mouse_move`, `kvm_mouse_move_pct`, `kvm_mouse_click`, `kvm_mouse_scroll`, `kvm_screenshot`, `kvm_screenshot_to_file`, `kvm_ocr_screenshot`, `kvm_ocr_click`, `comet_atx_power`, `comet_atx_click`, `comet_sysinfo`, and `comet_msd_upload`.

The 10 `comet_raw_*` aliases duplicate `kvm_*` tools and are deprecated in documentation only. Do not remove them in this docs pass; `tests/test_smoke.py` currently expects `comet_raw_send_keys` and `comet_raw_screenshot`.

## D-K2 — ATX power control is wrapped

ATX power control is available through `comet_atx_power` and `comet_atx_click`. These tools supersede the stale AGENTS.md claim that ATX endpoints are not wrapped. The tools still require the ATX add-on board to be physically installed and wired to the target.

## D-K3 — Upstream sync is fetch-only and selective

Keep `upstream` pointing at `kennypeh85/glkvm-mcp` as a fetch-only remote. Selectively cherry-pick upstream bug fixes or API improvements when relevant. This repo is not a mirror, not an upstream PR staging area, and does not track upstream releases.

## D-K4 — Watchdog and pinger are core firmware workarounds

The stale key watchdog and WebSocket pinger are required KVM-core reliability mechanisms. The watchdog runs every 40ms and force-releases keys held longer than 250ms. The pinger sends WebSocket pings every 1s to prevent kvmd timeout. These are firmware/API workarounds, not policy or approval mechanisms.

## D-K5 — Security model is LAN-first with per-session password

The Comet is operated on a trusted LAN or through Tailscale/VPN. TLS verification is disabled because the device uses a self-signed certificate. The password is supplied per session via `kvm_connect` or injected into the MCP process as `COMET_PASSWORD`; no Comet password is committed to the repository. `GLCOMET_ADMIN_PASSWORD` is accepted as a legacy environment-variable name for that same secret.

## D-K6 — PEP 723 script deployment remains the target

`glkvm_mcp.py` remains the single-script MCP entry point intended for `uv run --script`. The PEP 723 metadata includes the sidecar dependencies, including `instructor` and `litellm`, so script-only launches resolve the same runtime surface as the project environment.
