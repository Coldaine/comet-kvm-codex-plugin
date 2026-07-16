# Comet KVM Plugin

| | |
|---|---|
| **This repo** | [`Coldaine/comet-kvm-codex-plugin`](https://github.com/Coldaine/comet-kvm-codex-plugin) |
| **Forked from** | [`kennypeh85/glkvm-mcp`](https://github.com/kennypeh85/glkvm-mcp) (upstream MCP server) |
| **Relationship** | Selective fork — occasionally review upstream for bug fixes, but this repo diverges strongly and is its own project |

This repository develops and ships a **Comet KVM MCP server** for physical-machine triage, packaged for Codex as a plugin. The MCP server is the product: keyboard/mouse, screenshots, OCR, Comet hardware control, plus BIOS-aware tools (loaded by default; disable with `COMET_DISABLE_BIOS_SIDECAR=1`). The Codex plugin is how that server (and its driver skill) get installed. Not VM orchestration or general-purpose remote desktop.

**Primary distribution target: Codex.** The MCP server itself is usable from any MCP client; Codex packaging is first. See [`docs/NORTH_STAR.md`](docs/NORTH_STAR.md) for goals.

---

## What ships where

A Codex plugin is an installable bundle. For this project that bundle is:

| Plugin payload | Role |
|---|---|
| `.codex-plugin/plugin.json` | Manifest — identity + pointers |
| `.mcp.json` | How Codex launches **this repo's** MCP server |
| `skills/` | Driver playbooks (e.g. BIOS triage) |
| `glkvm_mcp.py` + `src/` | The MCP server implementation the launcher runs |

That is the whole plugin shape: **your MCP + skill(s)**. It is not a thin wrapper around upstream. Upstream (`kennypeh85/glkvm-mcp`) was the starting fork; this tree owns and augments the server.

### Not part of the plugin

These live in the repo for development and local agent work. They are **not** Codex plugin components:

| Repo surface | Role |
|---|---|
| `AGENTS.md` | Developer-agent guidance when working *in* this repo |
| `docs/` | Project authority and design docs |
| `scripts/`, `tests/`, `extras/` | Local tooling, tests, preserved upstream helpers |

`AGENTS.md` is project guidance (Codex loads it from the repo). Skills are workflows. MCP is tools. The plugin packages skills + MCP — not `AGENTS.md`.

### Repo layout

```
comet-kvm-codex-plugin/
├── .codex-plugin/
│   └── plugin.json          # Codex plugin manifest → skills + MCP
├── .mcp.json                # Launches this repo's MCP server
├── glkvm_mcp.py             # PEP 723 MCP entry point
├── src/
│   ├── kvm_core/            # Universal KVM transport, OCR, tools, runtime
│   └── bios_sidecar/        # BIOS-aware tools (default on; one-way dep on kvm_core)
├── skills/                  # Bundled driver skills (plugin payload)
│   └── comet-bios-triage/
├── AGENTS.md                # Repo developer guidance (not plugin payload)
├── docs/                    # Design / authority docs (not plugin payload)
├── scripts/                 # Local tooling (preflight, run ledger)
├── extras/                  # Upstream helpers (calibration, click helper, userscript)
├── runs/                    # Experiment records (gitignored)
├── state/                   # Runtime state (gitignored)
└── tests/
```

### Manifest

`.codex-plugin/plugin.json` points at the plugin payload only:

```json
{
  "skills": "./skills/",
  "mcpServers": "./.mcp.json"
}
```

`.mcp.json` starts `glkvm_mcp.py` (via Doppler + `uv run --locked --python 3.13 python ./glkvm_mcp.py` in this repo's launcher). The server code that runs is this project's — `kvm_core` plus `bios_sidecar` (loaded by default; set `COMET_DISABLE_BIOS_SIDECAR=1` to skip) on one `FastMCP("comet-kvm")` process. Dependency direction is one-way: sidecar may depend on KVM core, not vice versa.

---

## Current Scope

This is **one integrated spike** with two layers maturing in parallel: the universal KVM MCP server (transport, OCR, plugin packaging, session/auth) and the BIOS sidecar (cartography, navigation, mutation). The live-hardware proof point on MSI Z690 is **Planned** — code exists but has not yet been validated end-to-end against a real board.

**First spike — BIOS cartography:** A tool that near-exhaustively crawls the non-blocklisted zones of a target board's BIOS — a Python DFS driver for navigation, a VLM for per-screen structured perception, cycle detection via perceptual hashing, and explicit blocklisting for destructive screens. Maps are persisted as labeled, reusable artifacts.

**Immediate workflow — MSI Z690 tuning:** Drive BIOS changes one setting at a time against stored maps, then validate in Windows via HWiNFO.

See:
- [`docs/NORTH_STAR.md`](docs/NORTH_STAR.md) — project goals
- [`docs/kvm-core.md`](docs/kvm-core.md) — KVM MCP server architecture, tool surface, and KVM/BIOS sidecar boundary
- [`docs/architecture.md`](docs/architecture.md) — repo layout, sidecar shape, and known architecture gaps
- [`docs/decisions.md`](docs/decisions.md) — implementation decisions
- [`docs/vlm-prompt-contract.md`](docs/vlm-prompt-contract.md) — VLM prompt draft + justification
- [`docs/reference/comet-hardware.md`](docs/reference/comet-hardware.md) — verified Comet hardware/platform facts
- [`docs/reference/comet-api.md`](docs/reference/comet-api.md) — verified Comet API/software surface

---

## Installation

### Prerequisites

- Python >= 3.10
- [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) installed on the host
- A GL.iNet Comet (GL-RM1) or PiKVM-compatible device on your LAN (firmware 1.9.0+)
- [uv](https://docs.astral.sh/uv/) for running the MCP server
- [Doppler CLI](https://docs.doppler.com/docs/install-cli) configured for `secrets_managment/dev` when using the bundled plugin launcher

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

The plugin is auto-discovered when the repo is installed as a Codex plugin. Its bundled launcher runs `uv run --locked --python 3.13 python ./glkvm_mcp.py`. `kvm_connect` fetches `GLCOMET_ADMIN_PASSWORD` from the Doppler CLI (`doppler.yaml`); the host must have Doppler installed and authenticated.

**Launcher note:** The bundled [`.mcp.json`](.mcp.json) does not wrap the process in `doppler run` for env injection. Doppler CLI auth on the host is required for password resolution — tracked alongside portable plugin installs in [issue #24](https://github.com/Coldaine/comet-kvm-codex-plugin/issues/24).

### Use as a standalone MCP server

Add to any MCP client config:

```json
{
  "mcpServers": {
    "comet-kvm": {
      "command": "uv",
      "args": ["run", "--locked", "--python", "3.13", "python", "/path/to/glkvm_mcp.py"]
    }
  }
}
```

---

## MCP Tools

### Connection
| Tool | Description |
|------|-------------|
| `kvm_connect(host, password?, username?)` | Connect to a Comet device; omitted password resolves from the MCP process environment |
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
| `kvm_ocr_status()` | Report native Comet OCR and host Tesseract availability |
| `kvm_ocr_text(psm?, languages?, prefer_native?, left?, top?, right?, bottom?)` | Native-first visible text with host Tesseract fallback and optional crop |
| `kvm_ocr_screenshot(search_text?, preview?, psm?)` | Host Tesseract OCR with ordered text/lines plus word coordinates |
| `kvm_ocr_click(text, button?, count?, search_area?)` | Find text via OCR and click it |

### Comet Hardware
| Tool | Description |
|------|-------------|
| `comet_atx_power(action)` | Power on/off/reset through the ATX add-on board |
| `comet_atx_click(button)` | Momentary power/reset button pulse through the ATX add-on board |
| `comet_sysinfo()` | Retrieve device metadata and capabilities |
| `comet_msd_upload(remote_path, local_path)` | Upload a host file to the Comet's `/userdata/media/` partition |

### BIOS Workflow (sidecar)

| Tool | Description |
|------|-------------|
| `bios_observe_state()` | Capture and parse current BIOS screen; sync position tracker |
| `bios_crawl_step()` | Execute one safe crawl transition (debug single-step) |
| `bios_crawl_region(max_depth?)` | DFS crawl of current BIOS region with cycle detection |
| `bios_navigate_to(target_node_id)` | Replay stored graph path to a target node |
| `bios_propose_setting_change(capability_id, desired_value)` | Plan and validate a setting change |
| `bios_apply_setting_change(capability_id, desired_value)` | Apply mutation with visual verification |
| `bios_save_and_reboot()` | F10 save with dialog verification, then reboot |
| `bios_abort_and_recover()` | Release keys and Escape back-out of modals |
| `bios_export_trace()` | Export replayable run trace JSON |

### Perception (sidecar)

| Tool | Description |
|------|-------------|
| `kvm_vlm_parse(screenshot_ref, previous_state_id?, last_action?)` | VLM structured parse of a cached screenshot |
| `kvm_match_screen(screenshot_ref, expected_node_id?)` | Local phash + OCR fingerprint match against graph |

### MCP Resources (sidecar)

| URI | Description |
|-----|-------------|
| `bios://state/current` | Latest normalized BIOS state (JSON) |
| `bios://screen/current` | Current screenshot bytes (known limitation: see R1c) |
| `bios://graph/current` | Navigation graph summary (nodes + edges) |
| `bios://capabilities/current` | Discovered settings capability index |

See [`docs/kvm-core.md`](docs/kvm-core.md) for the BIOS interaction lifecycle.

### Deprecated Aliases

The `comet_raw_*` aliases currently duplicate `kvm_*` tools. They are deprecated in documentation only; the tools still exist and removal is a future code task.

---

## Architecture

```
┌──────────────┐     MCP stdio      ┌─────────────────┐     HTTPS/WSS     ┌──────────┐
│  AI Agent    │ ◄─────────────────► │  glkvm_mcp.py   │ ◄───────────────► │  Comet   │
│ (Codex)      │    tool calls       │  (MCP server)   │   (PiKVM API)     │  (GL-RM1)│
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

The MCP server maintains a persistent WebSocket connection to the Comet for low-latency keyboard/mouse input, and uses HTTP for screenshots, authentication, ATX, sysinfo, and MSD upload. It runs background key-watchdog and WebSocket-pinger loops.

Runtime logs go to stderr and to the rotating file `state/logs/comet-kvm.log`. Set `COMET_LOG_LEVEL` or `COMET_LOG_DIR` to override the default level or directory.

See [`docs/kvm-core.md`](docs/kvm-core.md) for the KVM core architecture and [`docs/reference/comet-api.md`](docs/reference/comet-api.md) for verified Comet API details.

---

## Security

- **LAN only** — designed for trusted local networks
- **TLS verification disabled** — the Comet ships with a self-signed certificate
- **No credentials stored** — password is passed per-session or fetched from Doppler CLI (`COMET_PASSWORD`)
- **Remote access** — use Tailscale (native on Comet) or VPN; do not expose the MCP server's stdio to an untrusted network

---

## Firmware Bug Fixes

This server includes fixes for known GLKVM/PiKVM firmware bugs:
- **Stuck key / double-typing** (firmware <= 1.9.0): every character sent as atomic keydown -> 25ms -> keyup(finish=true)
- **Modifier release order bug** (gl-inet/glkvm #22): modifiers wrap strictly outside the main key
- **Stale key watchdog**: auto-releases any key held >250ms

---

## Upstream Relationship

This repo is a selective fork of [`kennypeh85/glkvm-mcp`](https://github.com/kennypeh85/glkvm-mcp):

- **Upstream** is a standalone MCP server for GLKVM/Comet keyboard/mouse/screenshot/OCR.
- **This repo** ships its **own** MCP server (forked code under `src/`, composed by `glkvm_mcp.py`), augments it (BIOS sidecar, native OCR path, Comet hardware tools, etc.), and packages that server for Codex with skills.

We are not wrapping upstream as an external dependency. We keep a fetch-only `upstream` remote to cherry-pick bug fixes or API improvements when useful. This repo is not a mirror and does not track upstream releases.

Helpers that lived at upstream's repo root (calibration, click helper, stuck-key userscript) are preserved in [`extras/`](extras/) — useful, not plugin payload.

## License

MIT
