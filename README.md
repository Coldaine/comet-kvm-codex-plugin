# Comet KVM Plugin

A packaged plugin for GL.iNet Comet KVM-driven hardware triage workflows — BIOS configuration, pre-OS operations, and Windows-side validation on physical machines. Not VM orchestration or general-purpose remote desktop.

Forked from [`kennypeh85/glkvm-mcp`](https://github.com/kennypeh85/glkvm-mcp) (upstream MCP server) and packaged as a Codex plugin with a BIOS/HWiNFO triage skill and stateful workflow scaffolding.

**Primary target: Codex.** Cross-tool compatibility (Claude Code, Cursor, VS Code/Copilot) is designed in but deferred until the Codex plugin is proven. See [`docs/NORTHSTAR.md`](docs/NORTHSTAR.md) for goals.

---

## Plugin Architecture

This repo follows the **thin-manifest, shared-core** pattern that emerged across AI coding tools in 2025–2026. The idea: one repository, one set of shared resources, thin per-tool manifests that point at them. Adding a new tool later means adding one manifest file, not rewriting the plugin.

### How it's structured

```
comet-kvm-codex-plugin/
├── .codex-plugin/
│   └── plugin.json          # Codex plugin manifest (thin — points at shared resources)
├── .mcp.json                # MCP server config (tool-agnostic, any MCP client can use it)
├── AGENTS.md                # Operating rules (shared across tools)
├── glkvm_mcp.py             # The MCP server (single-file, PEP 723, tool-agnostic)
├── skills/                  # Agent Skills (agentskills.io open standard)
│   └── comet-bios-triage/
│       ├── SKILL.md
│       └── references/
├── scripts/                 # Local tooling (preflight, run ledger)
├── docs/                    # Project authority docs + reference material
│   ├── NORTHSTAR.md
│   ├── plans/
│   └── reference/
├── extras/                  # Upstream utilities (calibration, click helper, userscript)
├── runs/                    # Experiment records (gitignored content)
├── state/                   # Runtime state (gitignored content)
└── tests/
```

### The three portable layers

1. **MCP server** (`glkvm_mcp.py` + `.mcp.json`) — the universal tool-integration layer. MCP (Model Context Protocol) is supported by every major AI coding tool. The server is a single 904-line Python file using PEP 723 inline dependencies, launched via `uv run --script`. It works identically in Codex, Claude Code, Cursor, Kilo, or any MCP-compatible client without modification.

2. **Agent Skills** (`skills/*/SKILL.md`) — the universal instructions layer, following the [agentskills.io](https://agentskills.io) open standard. Skills are auto-discovered by Codex, Claude Code, Cursor, Kilo, OpenCode, Gemini CLI, and Cline. The `SKILL.md` format is the lowest common denominator across tools.

3. **Operating rules** (`AGENTS.md`) — shared agent instructions. Read natively by Codex, Claude Code, Cursor, and most modern tools.

### The thin manifest

`.codex-plugin/plugin.json` is the only Codex-specific file. It declares the plugin name, metadata, and points at the shared resources:

```json
{
  "skills": "./skills/",
  "mcpServers": "./.mcp.json",
  ...
}
```

No logic, no duplication — just a pointer. When cross-tool support is added later, a `.claude-plugin/plugin.json` or `.cursor-plugin/plugin.json` would be equally thin, pointing at the same `skills/` and `.mcp.json`.

### Why this pattern

- **MCP is the de facto common layer.** Every major AI coding tool supports MCP as its tool-integration mechanism. The server is written once, works everywhere.
- **SKILL.md is the de facto instructions standard.** Adopted across the tool ecosystem per agentskills.io. Skills are portable without translation.
- **Per-tool manifests are converging.** The [Open Plugin Specification](https://github.com/vercel-labs/open-plugin-spec) (v1.0.0, April 2026) defines a vendor-neutral `.plugin/plugin.json` that VS Code/Copilot already auto-detects alongside vendor-specific manifests. Each tool keeps its own manifest dir (`.codex-plugin/`, `.claude-plugin/`, `.cursor-plugin/`) but they're thin pointers, not competing formats.
- **What doesn't port cleanly:** hooks (event vocabularies differ per tool), subagents, and permission policies. BIOS/HID safety logic is kept in the MCP server (portable) rather than in tool-specific hooks.

This pattern was validated by real-world multi-target plugins (e.g. [InventorLab](https://github.com/adam-inventorlab/InventorLab)) that ship to Codex + Claude Code + Cursor from a single repo using thin per-tool manifests.

---

## Current Scope

**First spike — BIOS cartography:** A tool that enumerates the complete UI tree of a target board's BIOS deterministically — a Python DFS driver for navigation, a VLM for per-screen structured perception, cycle detection via perceptual hashing. Maps are persisted as labeled, reusable artifacts.

**Immediate workflow — MSI Z690 tuning:** Drive BIOS changes one setting at a time against stored maps, then validate in Windows via HWiNFO.

See:
- [`docs/NORTHSTAR.md`](docs/NORTHSTAR.md) — project goals
- [`docs/plans/comet-kvm-codex-plugin.md`](docs/plans/comet-kvm-codex-plugin.md) — implementation plan
- [`docs/reference/comet-hardware.md`](docs/reference/comet-hardware.md) — verified Comet hardware/platform facts
- [`docs/reference/comet-api.md`](docs/reference/comet-api.md) — verified Comet API/software surface

---

## Installation

### Prerequisites

- Python >= 3.10
- [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) installed on the host
- A GL.iNet Comet (GL-RM1) or PiKVM-compatible device on your LAN (firmware 1.9.0+)
- [uv](https://docs.astral.sh/uv/) for running the MCP server

### Install Tesseract

```bash
# Windows
choco install tesseract-ocr

# macOS
brew install tesseract

# Linux (Debian/Ubuntu)
sudo apt-get install tesseract-ocr
```

### Use in Codex

The plugin is auto-discovered when the repo is installed as a Codex plugin. The MCP server (`glkvm_mcp.py`) is launched via `uv run --script` with dependencies auto-installed from PEP 723 inline metadata.

### Use as a standalone MCP server

Add to any MCP client config:

```json
{
  "mcpServers": {
    "comet-kvm": {
      "command": "uv",
      "args": ["run", "--script", "/path/to/glkvm_mcp.py"]
    }
  }
}
```

---

## MCP Tools

### Connection
| Tool | Description |
|------|-------------|
| `kvm_connect(host, password, username?)` | Connect to a Comet device on the LAN |
| `kvm_disconnect()` | Close the session |
| `kvm_status()` | Report connection state and held keys |

### Keyboard
| Tool | Description |
|------|-------------|
| `kvm_send_text(text, wpm?)` | Type a string (atomic press pattern fixes stuck-key bug) |
| `kvm_send_keys(combo)` | Send a key chord (e.g. "Ctrl+Alt+Delete", "F5", "Win+L") |
| `kvm_hold_key(key, duration_ms)` | Press and hold a key (for auto-repeat scrolling) |
| `kvm_release_all()` | Force-release all held keys |

### Mouse
| Tool | Description |
|------|-------------|
| `kvm_mouse_move(x, y)` | Move to absolute int16 coordinates |
| `kvm_mouse_move_pct(x_pct, y_pct)` | Move to percentage of screen (0,0 = top-left) |
| `kvm_mouse_click(button?, count?)` | Click at current position |
| `kvm_mouse_scroll(dx?, dy?)` | Scroll the mouse wheel |

### Screenshot / OCR
| Tool | Description |
|------|-------------|
| `kvm_screenshot(preview?, max_width?, quality?)` | Capture JPEG frame as MCP image content |
| `kvm_screenshot_to_file(path, ...)` | Capture and save to disk |
| `kvm_ocr_screenshot(search_text?, preview?)` | Capture + Tesseract OCR: returns all text with coordinates |
| `kvm_ocr_click(text, button?, count?, search_area?)` | Find text via OCR and click it |

---

## Architecture

```
┌──────────────┐     MCP stdio      ┌─────────────────┐     HTTPS/WSS     ┌──────────┐
│  AI Agent    │ ◄─────────────────► │  glkvm_mcp.py   │ ◄───────────────► │  Comet   │
│ (Codex)      │    tool calls       │  (MCP server)   │   (PiKVM API)     │  (GL-RM1)│
└──────────────┘                     └─────────────────┘                   └──────────┘
                                             │
                                      Tesseract OCR
                                      (host-side)
```

The MCP server maintains a persistent WebSocket connection to the Comet for low-latency keyboard/mouse input, and uses HTTP for screenshots and authentication. It already runs two background asyncio loops (key watchdog + WebSocket pinger) — the planned state engine will join as a third.

See [`docs/reference/comet-api.md`](docs/reference/comet-api.md) for the full API surface and internal architecture details.

---

## Security

- **LAN only** — designed for trusted local networks
- **TLS verification disabled** — the Comet ships with a self-signed certificate
- **No credentials stored** — password is passed per-session via `kvm_connect`
- **Remote access** — use Tailscale (native on Comet) or VPN; do not expose the MCP server's stdio to an untrusted network

---

## Firmware Bug Fixes

This server includes fixes for known GLKVM/PiKVM firmware bugs:
- **Stuck key / double-typing** (firmware <= 1.9.0): every character sent as atomic keydown -> 25ms -> keyup(finish=true)
- **Modifier release order bug** (gl-inet/glkvm #22): modifiers wrap strictly outside the main key
- **Stale key watchdog**: auto-releases any key held >250ms

---

## Upstream

This is a fork of [`kennypeh85/glkvm-mcp`](https://github.com/kennypeh85/glkvm-mcp). The `upstream` remote is kept for manual review of upstream updates. Upstream helper utilities (screenshot calibration, click helper) are preserved in [`extras/`](extras/).

## License

MIT
