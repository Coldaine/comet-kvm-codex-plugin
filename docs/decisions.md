# Implementation Decisions

> **Repo:** `Coldaine/comet-kvm-codex-plugin` (fork of `kennypeh85/glkvm-mcp`)
> **Authority:** #2 in the [Authority Order](NORTH_STAR.md#authority-order). These are decisions about *how* we build the thing, not *what* the thing is (that's NORTH_STAR.md) or *how to behave* in the repo (that's AGENTS.md). See `docs/architecture.md` for the full justification of each decision.

## D1 — Screenshot retention: TTL, not permanent

Runtime screenshots are persisted temporarily for retry, debugging, and map-building, then automatically purged after approximately 30 days. They are never committed to Git. The retention is a cleanup policy, not a git policy — the TTL runs against whatever runtime data directory the installed plugin uses (host-side or on-Comet).

## D2 — Packaging end-state: plugin, not eternal Git repo

This project's end state is a packaged plugin distributed for installation, not a Git repo that accumulates runtime data forever. The Git repo is the *source* of the package. Runtime artifacts (BIOS maps, screenshots, experiment records) live in the install location at runtime, not in the repo source tree. This is why maps are not committed — they're user data, not project knowledge.

## D3 — Cartography skill placement: reference under active plans

BIOS cartography is a specialized subset of the `comet-bios-triage` skill, not a sibling skill. It is documented under `docs/architecture.md` and active plans (e.g. `docs/plans/01-vlm-mcp-integration-plan.md`). The existing skill's trigger surface already covers BIOS workflows; cartography is a prerequisite step within that workflow, not a separate capability.

## D4 — Map store runtime location: on-Comet preferred, pending verification

BIOS maps should persist on the Comet device itself, co-located with the hardware they describe. The Comet (GL-RM1) has 8GB eMMC with ~5.3GB free at `/userdata/media`, confirmed via root shell evidence in gl-inet/glkvm#14. A BIOS map is ~30-40MB, so the device has two orders of magnitude more storage than needed.

**Probe result (2026-07-07):** The Comet at `192.168.0.126` is reachable via HTTP (200 OK, PiKVM-fork nginx) and SSH (port 22 open, accepts publickey+password auth). However, SSH credentials are needed to verify `/userdata/media` writability and free space on this specific device. The device is architecturally suitable but storage writability is **unverified without credentials**.

**Fallback:** If on-Comet storage proves impractical, maps persist in the host-side plugin data directory. The VLM interpretation layer always runs on the host (the Comet has no GPU) regardless of where maps are stored.

## D5 — Fuzzy matching against similar boards: future MCP tool

The ability to match a live screen against stored maps from *similar* boards (not just the exact same board/BIOS-version) is a future capability. It will be exposed as an MCP tool that the calling LLM can invoke to investigate matches. The exact matching algorithm (perceptual hash similarity threshold, OCR text overlap, graph topology comparison) is not yet designed.

## D6 — glkvm_mcp.py file structure: not a hard constraint

`glkvm_mcp.py` is currently a single-file MCP server. It already runs two background asyncio loops (watchdog + pinger) and holds session state. The planned state engine will join as a third background loop in the same file. This is not a hard constraint — if the file's complexity grows past the point where a single file is maintainable (e.g. after adding the state engine and crawler-driving hooks), it may be split into modules within the same package. That split, if it comes, separates transport (Comet API client) from state (session, polling, map-matching) from OCR (Tesseract integration) — not into separate MCP servers.

## D7 — State engine deployment: internal asyncio tracking

The stateful screen-level position tracker runs inside the MCP server process, keeping track of which graph node the session is currently on. Instead of running a background loop that constantly polls (which is slow and expensive), the state tracker is updated on-demand when the Driver Agent calls tools like `bios_observe_state`, `bios_navigate_to`, or `bios_apply_setting_change`. The MCP server matches screens locally using perceptual hashes and OCR fingerprints (`kvm_match_screen`), calling the VLM tool (`kvm_vlm_parse`) only when grounding is needed.

## D8 — Two granularity levels: workflow phases vs screen position

The project operates at two distinct granularity levels that complement, not replace, each other:

- **Workflow level** (`stateful-control-model.md`): phases like `planned → preflight → bios-entry → bios-edit → save-confirm → windows-boot → hwinfo-log → analysis → done`. Agent-maintained, persisted in the run ledger. Asks "are we in the edit phase?"
- **Screen level** (state engine): which BIOS menu node are we on right now, matched against a stored map. Background-maintained, ephemeral per session. Asks "are we on the Overclocking submenu row 3, and did that Enter press land where the map predicted?"

Neither subsumes the other. The workflow phase model governs the experiment lifecycle; the screen-level state engine governs live navigation safety within a phase.

## D9 — Output format: Semantic Capability Index + screen-node graph

The crawler produces two views of the same crawl data:

- **Semantic Capability Index** (for the driver agent): a JSON file keyed by setting name, containing the navigation path, UI type, available options, and interaction keys. The driver reads this to navigate deterministically without calling the VLM.
- **Screen-node graph** (for the state engine): a network of screen nodes keyed by perceptual hash + OCR fingerprint, with edges labeled by the keystroke that transitions between them. The state engine matches live screenshots against these nodes for transition validation.

The crawler produces the graph (raw crawl data). A post-processing step derives the index from the graph. Both are persisted. See `docs/architecture.md` §9 for the full rationale.

## D10 — VLM framework: `instructor` + `litellm`, not hand-rolled

We do not build our own VLM transport, retry, or JSON-repair logic. We adopt two well-maintained libraries:

- **`litellm`** provides one call interface across providers. A single `model` string selects an OpenRouter vision model (`openrouter/qwen/qwen-2-vl-72b-instruct`, `openrouter/google/gemini-flash-1.5`, etc.) or a locally served small VLM (`ollama/llama3.2-vision`, `ollama/qwen2.5-vl`, or a vLLM OpenAI-compatible endpoint). This satisfies the "OpenRouter vision model OR local small LLM" requirement without provider-specific code.
- **`instructor`** wraps the call to return a Pydantic-validated object mapping onto `BiosState`. It handles corrective retries on malformed JSON, replacing the hand-rolled 3-attempt retry loop in `src/bios_sidecar/perception/vlm_client.py`.

Provider selection is by environment (`VLM_PROVIDER`, `VLM_MODEL`, `VLM_BASE_URL`, `OPENROUTER_API_KEY`). `mock` remains the default for tests and offline development. Only `OPENROUTER_API_KEY` is a secret (Doppler); local serving needs no key. See `docs/plans/01-vlm-mcp-integration-plan.md` §3.

## D11 — Tool surface granularity: phase-preserving, three-tier

The MCP surface exposes a compact but phase-preserving set of stateful, policy-gated `bios_*` tools (Tier 1), inspection resources (Tier 2), and segregated raw/perception primitives (Tier 3). We reject both the collapsed single-tool surface (`bios_set_setting`) — which would hold the KVM session hostage during out-of-band human approval and erase the observe/crawl/navigate/propose/apply/save/recover/trace seams — and the "raw HID everywhere" surface that lets the driver agent bypass policy gating. The driver agent gets semantic tools, not key-by-key tools. Human approval is out-of-band; the driver never self-approves. See `docs/plans/01-vlm-mcp-integration-plan.md` §2.
