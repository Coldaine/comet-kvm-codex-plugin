# Architecture

> **Repo:** `Coldaine/comet-kvm-codex-plugin` (fork of `kennypeh85/glkvm-mcp`)
> **Compiled:** 2026-07-07
> **Purpose:** Explain how this repo is laid out, how the existing code works, and why every architectural choice was made. This is the comprehensive "how and why" document — `docs/NORTH_STAR.md` says what we're building, `docs/decisions.md` records the decisions, this document explains the structure and justifies the choices.

## 1. Repo Layout

```
comet-kvm-codex-plugin/
├── .codex-plugin/
│   └── plugin.json          # Codex plugin manifest (thin — points at shared resources)
├── .mcp.json                # MCP server config (tool-agnostic, any MCP client can use it)
├── AGENTS.md                # Operating rules for the developer agent (repo conventions)
├── glkvm_mcp.py             # The MCP server (single-file, PEP 723, tool-agnostic)
├── skills/                  # Agent Skills (agentskills.io open standard)
│   └── comet-bios-triage/   # The BIOS triage skill (instructs the driver agent)
│       ├── SKILL.md
│       └── references/
│           ├── stateful-control-model.md
│           ├── bios-cartography.md       # Prior design draft (superseded by this doc)
│           ├── msi-z690-bios-workflow.md
│           └── hwinfo-run-loop.md
├── scripts/                 # Local tooling
│   ├── comet_preflight.py   # Host checks (local-only, no KVM actions)
│   └── run_ledger.py        # Experiment record creation/update
├── docs/                    # Project authority docs + design docs
│   ├── NORTH_STAR.md        # Goals (top-level authority)
│   ├── decisions.md         # Implementation decisions
│   ├── architecture.md      # This document
│   ├── vlm-prompt-contract.md  # VLM prompt draft + justification
│   └── reference/           # Verified facts about external systems
│       ├── comet-hardware.md
│       └── comet-api.md
├── extras/                  # Upstream utilities (not plugin core)
│   ├── kvm_calibrate.py
│   ├── kvm_click_helper.py
│   └── glkvm-stuck-key-fix.user.js
├── runs/                    # Experiment records (runtime, gitignored)
├── state/                   # Runtime state (gitignored)
└── tests/
    └── test_smoke.py        # Tool-registration smoke test
```

### Why this layout

The repo follows the **thin-manifest, shared-core** pattern: one repository, one set of shared resources, thin per-tool manifests that point at them. The three portable layers — MCP server, Agent Skills, operating rules — are tool-agnostic. The only Codex-specific file is `.codex-plugin/plugin.json`, which is a thin pointer. Adding cross-tool support later means adding one manifest file, not rewriting the plugin.

See `README.md` § Plugin Architecture for the thin-manifest pattern rationale and the agentskills.io / Open Plugin Spec references.

### What goes where

| Content type | Location | Why |
|-------------|----------|-----|
| Goals (what we're building) | `docs/NORTH_STAR.md` | Top-level authority, read first |
| Implementation decisions (how we build it) | `docs/decisions.md` | Separate from goals; decisions can change |
| Architecture explanation (how + why) | `docs/architecture.md` (this doc) | Design rationale, code structure, runtime composition |
| VLM prompt contract | `docs/vlm-prompt-contract.md` | Design artifact that will become code; not a skill |
| Verified external facts | `docs/reference/` | Hardware specs, API surface — cited, dated |
| Developer agent rules | `AGENTS.md` | Repo conventions for code editing |
| Driver agent rules | `skills/comet-bios-triage/` | Runtime KVM operation instructions |
| Upstream utilities | `extras/` | Not plugin core, preserved from upstream |
| Runtime data | `runs/`, `state/` | Gitignored; never committed |

## 2. How glkvm_mcp.py Works

### Single-file PEP 723 MCP server

`glkvm_mcp.py` is a self-contained Python file that serves as the entire MCP server. It uses PEP 723 inline script metadata to declare dependencies, so it can be run with `uv run --script ./glkvm_mcp.py` without a separate `requirements.txt` or virtual environment setup. Dependencies (`mcp[cli]`, `websockets`, `httpx`, `Pillow`, `pytesseract`) are auto-installed by `uv` on first run.

The server uses `FastMCP` from the `mcp.server.fastmcp` module — a high-level MCP server framework that lets tools be defined as decorated async Python functions.

### Connection state

The server maintains a single global `Connection` dataclass (line 158):

```python
@dataclass
class Connection:
    base_url: str                    # e.g., "https://192.168.8.55"
    http: httpx.AsyncClient           # HTTP client for screenshots + auth
    ws: websockets.WebSocketClientProtocol  # WebSocket for keyboard/mouse
    held: dict[str, float]            # key -> down_at (monotonic) for watchdog
    send_lock: asyncio.Lock           # serializes WS sends
    watchdog: Optional[asyncio.Task]  # background key-watchdog task
    pinger: Optional[asyncio.Task]    # background WebSocket ping task
```

A single `_conn` global holds the active connection. `kvm_connect` creates it, `kvm_disconnect` tears it down. All other tools call `_require_conn()` to access it.

### The three API endpoints

The server exercises exactly three endpoints on the Comet:

1. **`POST /api/auth/login`** — authentication. `kvm_connect` sends username + password, receives an `auth_token` cookie. If `two_step_required` is true, 2FA is needed (not currently handled).

2. **`WSS /api/ws?auth_token=<token>&stream=false`** — WebSocket for keyboard/mouse input. `stream=false` means video is not carried over the WebSocket; screenshots use the HTTP endpoint instead. A pinger loop keeps the connection alive.

3. **`GET /api/streamer/snapshot`** — JPEG frame capture. Used by `kvm_screenshot`, `kvm_screenshot_to_file`, `kvm_ocr_screenshot`, and `kvm_ocr_click`. Parameters control preview mode, max width, and JPEG quality.

### Background asyncio loops

The server already runs two background asyncio tasks per connection — this is the existing pattern the state engine will follow as a third:

**`_watchdog_loop` (40ms period, line 180):**
- Monitors the `held` dict for keys that have been down longer than `STALE_S` (250ms).
- Force-releases stale keys via WebSocket.
- Prevents stuck keys from interrupted or failed input sequences.
- Uses `conn.send_lock` to avoid racing with concurrent input sends.

**`_pinger_loop` (1s period, line 199):**
- Sends WebSocket ping frames to keep the connection alive.
- PiKVM's kvmd drops connections after ~15 missed pings; this prevents that.

### Key/mouse input protocol

Keyboard events are sent as W3C KeyboardEvent codes over WebSocket:
- `_ws_send_key(conn, key, state, finish)` — sends keydown (state=True) or keyup (state=False). `finish=True` on keyup matches the PiKVM protocol.
- `_atomic_press(conn, key, hold_s)` — the core of the stuck-key fix: keydown → 25ms → keyup(finish=true). Every character in `kvm_send_text` uses this pattern.
- `_press_with_modifiers(conn, key, modifiers)` — modifiers wrap strictly outside the main key: mods down → key down → key up → mods up. Fixes gl-inet/glkvm #22.

Mouse events use absolute int16 coordinates or percentage-based positioning:
- `_ws_send_mouse_move(conn, x, y)` — absolute coordinates.
- `kvm_mouse_move_pct` converts percentages to int16 coordinates.

### OCR integration (Tesseract)

OCR runs on the host, not the Comet:
- `_find_tesseract_binary()` locates the Tesseract executable via env vars, PATH, or Windows default paths.
- `_run_ocr(image_bytes, search_text)` passes the JPEG to Tesseract via `pytesseract`, returns structured JSON with text, confidence, and coordinates.
- `kvm_ocr_screenshot` captures a frame + runs OCR + returns the structured result.
- `kvm_ocr_click` captures + OCR + finds text + clicks its coordinates — an all-in-one tool.

### Tool registration

All 15 tools are registered via `@mcp.tool(annotations={...})` decorators. Each annotation declares whether the tool is read-only, destructive, and/or idempotent. This metadata helps MCP clients (and the driver agent) understand the safety profile of each tool before calling it.

### Why a single file

The single-file design works for the current scope: one transport layer, 15 tools, two background loops, OCR integration. It's self-contained and easy to deploy via `uv run --script`. As the state engine (3rd asyncio loop + screen polling + map matching) and potentially crawler-driving hooks are added, the file may be split into modules within the same package — but not into separate MCP servers. See `docs/decisions.md` D6.

## 3. Three-Agent Topology

### The problem

Building a BIOS triage tool involves three fundamentally different concerns that, if conflated, produce architecture that serves none of them well:

1. **Editing the plugin's source code** — a developer concern. Needs repo conventions, git hygiene, upstream sync rules, knowledge of where authority documents live.
2. **Operating the Comet KVM at runtime** — a driver concern. Needs BIOS navigation safety rules, one-change-per-run discipline, knowledge of the stateful control model, understanding of when to release keys and when to abort.
3. **Perceiving BIOS screens** — a perception concern. Needs a fixed prompt/schema contract, temperature 0 for reproducibility, a UI element taxonomy, a blocklist of dangerous keywords to flag. Does not need to know about git, repo structure, or the stateful control model.

### The solution

Three distinct instruction surfaces, one per concern:

| Role | Instructions live in | Concern |
|------|---------------------|---------|
| Developer agent | `AGENTS.md` + `docs/NORTH_STAR.md` + `docs/decisions.md` | Source code |
| Driver agent | `skills/comet-bios-triage/SKILL.md` + references | Runtime KVM operation |
| VLM agent | VLM prompt/schema contract (in the cartographer tool) | Screen perception |

The same agent instance may fill multiple roles — the developer agent can switch to the driver role when operating the Comet. The distinction is about which instruction surface applies in the moment, not about agent identity.

### Why this matters

If driver-agent safety rules are put in AGENTS.md, the developer agent is burdened with rules that don't apply to code editing, and the driver agent might not find them because it reads the skill files. If VLM-agent prompt instructions are put in the skill files, the VLM never sees them — it's a service that receives a prompt at call time, not an agent that reads markdown files.

## 4. VLM as Perception Service, Not Navigator

### Why VLM-as-navigator fails for BIOS

1. **BIOS has no accessibility tree.** Desktop GUI agents rely on accessibility APIs (UIAutomation, AT-SPI, DOM). BIOS renders its own canvas — there is no semantic tree behind the pixels. The Set-of-Marks vs. pixel-in-action-out debate is a desktop GUI debate that doesn't transfer to firmware.

2. **BIOS action space is keyboard, not coordinates.** Comet's reliable path is `kvm_key` with Tab/Enter/arrows. Mouse in BIOS is vendor-dependent and flaky. A model trained to emit (x,y) click coordinates is outputting the wrong modality.

3. **Goal-conditioned agents avoid exhaustive behavior.** Pixel-in-action-out models are RL-tuned to take the shortest path to a goal. A BIOS crawler wants the opposite: visit every reachable screen. Goal-conditioned agents actively avoid the exhaustive behavior the crawler needs.

4. **Non-determinism is unacceptable for a crawler.** If the VLM picks actions, two crawls of the same BIOS may produce different maps. The whole point of cartography is a reproducible artifact.

### Why VLM-as-perceiver works

The VLM's strength is structured perception — reading what's on a screen and returning a labeled description. Its weakness is action selection. By constraining the VLM to perception only:

- The deterministic Python driver owns navigation. Two crawls of the same BIOS produce identical navigation sequences.
- The VLM's output is a structured JSON parse per screen. At temperature 0 with a strict schema, two parses of the same screenshot produce identical JSON.
- The crawler's map is reproducible because both layers are deterministic.
- The VLM can be swapped or upgraded without changing the driver logic, as long as it honors the same schema.

The VLM never sends keystrokes. It never picks a menu item. It only answers: "what is on this screen?" See `docs/vlm-prompt-contract.md` for the full prompt and schema.

## 5. Near-Exhaustive Crawl with Blocklisted Zones

### The risk

The crawler is intended to be read-only — it only sends navigation keys (Tab/arrows/Enter/Esc). But on some BIOS screens, Enter confirms a destructive action (Flash, Secure Erase) rather than navigating into a submenu. The crawler can't always distinguish a navigation Enter from a confirmation Enter.

### The chosen approach

Crawl every reachable screen in non-blocklisted zones. Blocklist zones where Enter = destructive action. The blocklist is a small, explicit list of screens where the navigation-as-confirmation risk is real:

| Blocklisted keyword | Why |
|---------------------|-----|
| Flash | Enter might start a firmware flash — irreversible |
| Secure Erase | Enter might start a drive wipe — data-destructive |
| RAID | Enter might change RAID mode — could destroy array membership |
| Boot Order | Enter might reorder boot devices + require a save the crawler shouldn't trigger |
| Password | Enter might set a BIOS password — could lock out future access |

The blocklist is not "things we don't care about" — it's "things where Enter could trigger an irreversible action." Settings tabs (OC, CPU, DRAM, Advanced) are NOT blocklisted because Enter navigates or opens an edit dialog, both safe to back out of.

The VLM detects blocklisted keywords on screen and flags them in its structured output. The driver checks the flag and backs out (Esc) without sending Enter. If a blocklisted zone is ever genuinely needed, the driver agent handles it manually — not the crawler.

## 6. Deterministic Navigation + VLM Perception Split

| Layer | Owner | Determinism |
|-------|-------|-------------|
| Navigation (keystroke selection) | Python DFS driver | Fully deterministic — same BIOS, same crawl sequence |
| Screen perception | VLM agent | Deterministic at temperature 0 with strict schema |
| Map storage | Python store | Deterministic — derived from the other two layers |
| State engine | Python asyncio loop | Deterministic — perceptual hash + OCR fingerprint matching |

Each responsibility is placed in the layer that can execute it deterministically. The VLM is used exactly where its strength matters (structured perception of non-standard UI) and nowhere else.

## 7. Why the VLM Cannot Run on the Comet

The Comet (GL-RM1) has a quad-core ARM Cortex-A7 @ 1.5GHz with no GPU. VLM inference requires GPU acceleration for practical latency. Running a 7B+ parameter VLM on a Cortex-A7 would take minutes per screen, making a 150-400 screen crawl take hours.

- The VLM runs on the **host machine** (or a network-accessible GPU server).
- The Comet is transport (screenshots, keystrokes) and storage (map files) only.
- The state engine runs on the host inside `glkvm_mcp.py` (an asyncio loop).

This is a hard constraint. See `docs/reference/comet-hardware.md` for verified hardware specs.

## 8. State Engine vs. VLM

The state engine runs continuously in the background during live BIOS sessions — it polls the screen, matches it against the stored map, and validates transitions. The VLM is wrong for this job because every poll would be a slow, expensive VLM API call.

Instead, the state engine uses perceptual hashing (`imagehash`) + OCR text fingerprinting to match live screenshots against stored map nodes. This is fast (microseconds for hash comparison, ~100ms for OCR), deterministic, and cheap (no VLM call needed).

The VLM is called only during the initial crawl (to build the map) and on-demand by the driver agent (to read a specific current value). The state engine never calls the VLM.

### Two granularity levels

1. **Workflow-level** (`stateful-control-model.md`): phases like `planned → preflight → bios-entry → bios-edit → save-confirm → …`. Maintained by the driver agent, persisted in the run ledger.
2. **Screen-level** (state engine): which BIOS menu node are we on right now. Maintained by the asyncio loop, ephemeral per session.

Neither subsumes the other. See `docs/decisions.md` D8.

## 9. Output Format: Semantic Capability Index + Screen Graph

The crawler produces a map that serves two consumers:

- **The driver agent** needs to navigate to a specific setting deterministically. "Change CPU Lite Load to Mode 3" → look up the path → replay keystrokes.
- **The state engine** needs to identify which screen the live session is on. This requires screen fingerprints (perceptual hash + OCR text), not just setting paths.

### Two views of the same data

- **Index view (for the driver agent):** a JSON file keyed by setting name, containing the navigation path, UI type, available options, and interaction keys. The driver reads this to navigate deterministically without calling the VLM.
- **Graph view (for the state engine):** a network of screen nodes keyed by perceptual hash + OCR fingerprint, with edges labeled by the keystroke that transitions between them. The state engine matches live screenshots against these nodes.

The crawler produces the graph (raw crawl data). A post-processing step derives the index from the graph. Both are persisted. The driver reads the index; the state engine reads the graph.

## 10. Runtime Composition

### During a crawl (cartography)

1. DFS driver requests a screenshot via MCP → Comet captures JPEG.
2. JPEG sent to VLM interpreter → VLM returns structured JSON parse.
3. DFS driver checks blocklist flag. If clear, decides next navigation keystroke based on the parse.
4. Keystroke sent via MCP → Comet sends it to the target machine.
5. Repeat until all reachable screens in non-blocklisted zones are visited.
6. Map store persists the graph + derived index.

### During a tuning session (driver agent + state engine)

1. Driver agent reads the index to find the path + interaction keys for the target setting.
2. Driver sends navigation keystrokes via MCP.
3. State engine polls the screen after each keystroke, matches against the stored graph, validates the transition.
4. If a transition is invalid (drift detected), the state engine raises an alarm. The driver stops and reassesses.
5. Once at the target setting, the driver changes the value (one change per run), screenshots before/after, and proceeds through the stateful control model.

The VLM is not called during a tuning session unless the driver explicitly requests a value read. Navigation is fully deterministic via the index.
