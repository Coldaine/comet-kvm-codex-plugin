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
│           ├── msi-z690-bios-workflow.md
│           └── hwinfo-run-loop.md
├── scripts/                 # Local tooling
│   ├── comet_preflight.py   # Host checks (local-only, no KVM actions)
│   └── run_ledger.py        # Experiment record creation/update
├── docs/                    # Project authority docs + design docs
│   ├── plans/               # Migration and integration plans
│   │   └── 01-vlm-mcp-integration-plan.md
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

---

## 2. How glkvm_mcp.py Works

### Single-file PEP 723 MCP server

`glkvm_mcp.py` is a self-contained Python file that serves as the entire MCP server. It uses PEP 723 inline script metadata to declare dependencies, so it can be run with `uv run --script ./glkvm_mcp.py` without a separate `requirements.txt` or virtual environment setup. Dependencies (`mcp[cli]`, `websockets`, `httpx`, `Pillow`, `pytesseract`) are auto-installed by `uv` on first run.

The server uses `FastMCP` from the `mcp.server.fastmcp` module — a high-level MCP server framework that lets tools be defined as decorated async Python functions.

### Connection state

The server maintains a single global `Connection` dataclass:

```python
@dataclass
class Connection:
    base_url: str                    # e.g., "https://192.168.0.126"
    http: httpx.AsyncClient           # HTTP client for screenshots + auth
    ws: websockets.WebSocketClientProtocol  # WebSocket for keyboard/mouse
    held: dict[str, float]            # key -> down_at (monotonic) for watchdog
    send_lock: asyncio.Lock           # serializes WS sends
    watchdog: Optional[asyncio.Task]  # background key-watchdog task
    pinger: Optional[asyncio.Task]    # background WebSocket ping task
```

A single `_conn` global holds the active connection. `kvm_connect` creates it, `kvm_disconnect` tears it down. All other tools call `_require_conn()` to access it.

### Background asyncio loops

The server runs two background asyncio tasks per connection:

**`_watchdog_loop` (40ms period):**
- Monitors the `held` dict for keys that have been down longer than `STALE_S` (250ms).
- Force-releases stale keys via WebSocket.
- Prevents stuck keys from interrupted or failed input sequences.

**`_pinger_loop` (1s period):**
- Sends WebSocket ping frames to keep the connection alive.
- PiKVM's kvmd drops connections after ~15 missed pings; this prevents that.

### Key/mouse input protocol

Keyboard events are sent as W3C KeyboardEvent codes over WebSocket. Modifiers wrap strictly outside the main key: mods down → key down → key up → mods up.

Mouse events use absolute int16 coordinates or percentage-based positioning.

### OCR and VLM integration (Tesseract & VLM Tool)

OCR and perception run on the host:
- Tesseract provides local OCR text mapping (`kvm_ocr_screenshot`, `kvm_ocr_click`).
- The VLM parses screenshots via the `kvm_vlm_parse` tool, ensuring the prompt, inputs, and JSON output are recorded in the MCP server's transaction log.

---

## 3. Three-Agent Topology

Building a BIOS triage tool involves three fundamentally different concerns that are divided into distinct roles:

1. **Developer Agent**: Writes the MCP tools, database storage schemas, and prompt contracts.
2. **Driver Agent** (Orchestrating LLM): Drives the KVM, manages the crawl stack, implements the DFS logic, handles navigation, and coordinates safety checks.
3. **VLM Agent** (Vision LLM): A stateless, pure-perception tool client. It receives screen images via `kvm_vlm_parse`, parses them, and returns JSON.

---

## 4. VLM as Perception Service, Not Navigator

The VLM's strength is structured perception — reading what's on a screen and returning a labeled description. Its weakness is action selection. By constraining the VLM to perception only:

* The deterministic Python driver or the Driver Agent owns navigation.
* The VLM's output is a structured JSON parse per screen. At temperature 0 with a strict schema, two parses of the same screenshot produce identical JSON.
* The VLM never sends keystrokes. It never picks a menu item. It only answers: "what is on this screen?" See `docs/vlm-prompt-contract.md` for the full prompt and schema.

---

## 5. Near-Exhaustive Crawl with Blocklisted Zones

The crawler is intended to be read-only — it only sends navigation keys (Tab/arrows/Enter/Esc). The blocklist is a small, explicit list of screens where the navigation-as-confirmation risk is real (Flash, Secure Erase, RAID, Boot Order, Password).

The VLM detects blocklisted keywords on screen and flags them in its structured output. The driver checks the flag and backs out (Esc) without sending Enter. If a blocklisted zone is ever genuinely needed, the driver agent handles it manually — not the crawler.

---

## 6. Why the VLM Cannot Run on the Comet

The Comet (GL-RM1) has a quad-core ARM Cortex-A7 @ 1.5GHz with no GPU. VLM inference requires GPU acceleration for practical latency. 

* The VLM runs on the **host machine** (or a network-accessible GPU server).
* The Comet is transport (screenshots, keystrokes) and preferred storage for map files.

---

## 7. State Engine vs. VLM

The stateful screen-level position tracker runs inside the MCP server process, keeping track of which graph node the session is currently on. Instead of running a background loop that constantly polls (which is slow and expensive), the state tracker is updated on-demand when the Driver Agent calls tools like `bios_observe_state` or `bios_set_setting`.

The MCP server matches screens locally using perceptual hashes and OCR fingerprints via the `kvm_match_screen` tool, calling the VLM tool (`kvm_vlm_parse`) only when grounding is needed.

---

## 8. Output Format: Semantic Capability Index + Screen Graph

The crawler produces two views of the same crawl data:

* **Index view (for the driver agent):** a JSON file keyed by setting name, containing the navigation path, UI type, available options, and interaction keys.
* **Graph view (for the state engine):** a network of screen nodes keyed by perceptual hash + OCR fingerprint, with edges labeled by the keystroke that transitions between them.

---

## 9. Runtime Composition (Tuning Session)

1. **Driver Agent** calls `bios_connect()`.
2. **Driver Agent** calls `bios_observe_state()`.
   * The stateful tracker captures the screen and calls `kvm_vlm_parse` to ground itself.
   * The VLM parses the screen, returns the JSON, and the tracker aligns the session to `"EZ Mode"`.
3. **Driver Agent** calls `bios_navigate_to("node_oc_settings")`.
   * The stateful tracker replays the keystroke path. It uses fast, local visual hashes and OCR fingerprints (`kvm_match_screen`) to track the cursor at each intermediate step without calling the VLM.
4. **Driver Agent** calls `bios_propose_setting_change(...)` -> generates a plan.
5. **[Operator grants approval out-of-band]**.
6. **Driver Agent** calls `bios_set_setting(capability_id, desired_value, approval_id)`.
   * The tracker navigates to the row, activates input, types the value directly, and hits Enter.
   * The tracker calls `kvm_vlm_parse` to visually verify the change.
7. **Driver Agent** calls `bios_save_and_reboot()`.
   * The tracker sends `"F10"`, calls the VLM to verify the confirm dialog is active, and hits `"Enter"`.
8. **Driver Agent** calls `bios_export_trace()` and `bios_disconnect()`.
