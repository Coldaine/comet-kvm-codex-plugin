# Implementation Decisions

> **Repo:** `Coldaine/comet-kvm-codex-plugin` (fork of `kennypeh85/glkvm-mcp`)
> **Authority:** #2 in the [Authority Order](NORTH_STAR.md#authority-order). These are decisions about *how* we build the thing, not *what* the thing is (that's NORTH_STAR.md) or *how to behave* in the repo (that's AGENTS.md).

## D1 — Screenshot retention: TTL, not permanent

Runtime screenshots are persisted temporarily for retry, debugging, and map-building, then automatically purged after approximately 30 days. They are never committed to Git. The retention is a cleanup policy, not a git policy — the TTL runs against whatever runtime data directory the installed plugin uses (host-side or on-Comet).

## D2 — Packaging end-state: plugin, not eternal Git repo

This project's end state is a packaged plugin distributed for installation, not a Git repo that accumulates runtime data forever. The Git repo is the *source* of the package. Runtime artifacts (BIOS maps, screenshots, experiment records) live in the install location at runtime, not in the repo source tree. This is why maps are not committed — they're user data, not project knowledge.

## D3 — Cartography skill placement: reference under comet-bios-triage

BIOS cartography is a specialized subset of the `comet-bios-triage` skill, not a sibling skill. It will be documented as a reference file under `skills/comet-bios-triage/references/` (e.g. `bios-cartography.md`). The existing skill's trigger surface already covers BIOS workflows; cartography is a prerequisite step within that workflow, not a separate capability.

## D4 — Map store runtime location: on-Comet preferred, pending verification

BIOS maps should persist on the Comet device itself, co-located with the hardware they describe. The Comet (GL-RM1) has 8GB eMMC with ~5.3GB free at `/userdata/media`, confirmed via root shell evidence in gl-inet/glkvm#14. A BIOS map is ~30-40MB, so the device has two orders of magnitude more storage than needed.

**Probe result (2026-07-07):** The Comet at `192.168.0.126` is reachable via HTTP (200 OK, PiKVM-fork nginx) and SSH (port 22 open, accepts publickey+password auth). However, SSH credentials are needed to verify `/userdata/media` writability and free space on this specific device. The device is architecturally suitable but storage writability is **unverified without credentials**.

**Fallback:** If on-Comet storage proves impractical, maps persist in the host-side plugin data directory. The VLM interpretation layer always runs on the host (the Comet has no GPU) regardless of where maps are stored.

## D5 — Fuzzy matching against similar boards: future MCP tool

The ability to match a live screen against stored maps from *similar* boards (not just the exact same board/BIOS-version) is a future capability. It will be exposed as an MCP tool that the calling LLM can invoke to investigate matches. The exact matching algorithm (perceptual hash similarity threshold, OCR text overlap, graph topology comparison) is not yet designed.

## D6 — glkvm_mcp.py file structure: not a hard constraint

`glkvm_mcp.py` is currently a single-file MCP server. It already runs two background asyncio loops (watchdog + pinger) and holds session state. The planned state engine will join as a third background loop in the same file. This is not a hard constraint — if the file's complexity grows past the point where a single file is maintainable (e.g. after adding the state engine and crawler-driving hooks), it may be split into modules within the same package. That split, if it comes, separates transport (Comet API client) from state (session, polling, map-matching) from OCR (Tesseract integration) — not into separate MCP servers.

## D7 — State engine deployment: internal asyncio loop

The stateful screen-level position tracker runs as an internal asyncio background task inside `glkvm_mcp.py`, joining the existing `_watchdog_loop` (40ms) and `_pinger_loop` (1s). It is exposed via read-only MCP tools (`kvm_current_screen`, `kvm_in_sync`, etc.). It is maintained by deterministic code, not the main LLM. The MCP server already holds session state and runs background tasks — this is the existing pattern, not new architecture.

## D8 — Two granularity levels: workflow phases vs screen position

The project operates at two distinct granularity levels that complement, not replace, each other:

- **Workflow level** (`stateful-control-model.md`): phases like `planned → preflight → bios-entry → bios-edit → save-confirm → windows-boot → hwinfo-log → analysis → done`. Agent-maintained, persisted in the run ledger. Asks "are we in the edit phase?"
- **Screen level** (state engine): which BIOS menu node are we on right now, matched against a stored map. Background-maintained, ephemeral per session. Asks "are we on the Overclocking submenu row 3, and did that Enter press land where the map predicted?"

Neither subsumes the other. The workflow phase model governs the experiment lifecycle; the screen-level state engine governs live navigation safety within a phase.
