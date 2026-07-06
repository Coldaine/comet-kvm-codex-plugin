# Comet KVM Codex Plugin

This repository is a Codex plugin fork of [`kennypeh85/glkvm-mcp`](https://github.com/kennypeh85/glkvm-mcp). The upstream MCP server remains the direct GL.iNet Comet/GLKVM control layer; this fork adds Codex plugin metadata, a BIOS/HWiNFO triage skill, and stateful workflow scaffolding.

Immediate target workflow:

1. Connect Codex to a GL.iNet Comet KVM through MCP.
2. Capture screenshots and OCR before taking action.
3. Drive MSI Z690 BIOS changes one setting at a time.
4. Boot Windows and collect HWiNFO logs.
5. Analyze thermal, voltage, power, throttling, and WHEA results before continuing.

See [`docs/plans/comet-kvm-codex-plugin.md`](docs/plans/comet-kvm-codex-plugin.md) for the implementation plan.

---

# Upstream GLKVM MCP Server

An [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) server that exposes a [GL.iNet GLKVM](https://www.gl-inet.com/products/gl-sg24/) / PiKVM-fork device's keyboard, mouse, and **OCR-enhanced screenshot** capabilities as AI agent tools.

Control a remote machine over IP-KVM — type, click, screenshot, and **read text off the screen** — all through structured MCP tool calls that any LLM agent (Claude, GPT, GLM, etc.) can use directly.

## ✨ Key Features

- **Full keyboard control** — type text, send key chords (Ctrl+Alt+Del, Win+L, F11), hold keys
- **Precise mouse control** — move, click, scroll, with percentage-based positioning (100% accurate)
- **Screenshot capture** — full-resolution or preview, returned as MCP image content
- **🔧 OCR-powered targeting** — built-in Tesseract OCR integration that:
  - Reads all text on the remote screen with exact pixel + percentage coordinates
  - Lets agents click on UI elements by **text name** instead of guessing coordinates
  - Eliminates the unreliable "vision model estimates pixel position" pattern

## 🎯 Why OCR Integration?

Vision models (GPT-4V, Claude Vision, GLM-4V) are great at *reading* screenshots but terrible at *estimating pixel coordinates* — often off by 30%+. Meanwhile, the KVM mouse is accurate to <0.5%. The bottleneck was always **knowing where to click**, not the clicking itself.

**Before (unreliable):**
```
Agent: "Where is the 'Day' button?" → Vision model: "around 45%, 15%" → Misses
```

**After (OCR-powered):**
```
Agent: kvm_ocr_click("Day") → OCR finds exact position → Clicks dead center → ✅
```

## 📦 Installation

### 1. Install Tesseract OCR (system dependency)

```bash
# Windows
choco install tesseract-ocr
# or download from https://github.com/UB-Mannheim/tesseract/wiki

# macOS
brew install tesseract

# Linux (Debian/Ubuntu)
sudo apt-get install tesseract-ocr
```

### 2. Configure in your MCP client

Add to your MCP client config (e.g., Claude Desktop `claude_desktop_config.json`, Hermes `config.yaml`):

```json
{
  "mcpServers": {
    "glkvm": {
      "command": "uv",
      "args": [
        "run",
        "--script",
        "/path/to/glkvm_mcp.py"
      ]
    }
  }
}
```

Python dependencies (`mcp`, `websockets`, `httpx`, `Pillow`, `pytesseract`) are auto-installed by `uv run --script` via the inline PEP 723 metadata.

## 🔧 Tools

### Connection
| Tool | Description |
|------|-------------|
| `kvm_connect(host, password, username?)` | Connect to a GLKVM device on the LAN |
| `kvm_disconnect()` | Close the session |
| `kvm_status()` | Report connection state and held keys |

### Keyboard
| Tool | Description |
|------|-------------|
| `kvm_send_text(text, wpm?)` | Type a string (atomic press pattern fixes stuck-key bug) |
| `kvm_send_keys(combo)` | Send a key chord (e.g., "Ctrl+Alt+Delete", "F5", "Win+L") |
| `kvm_hold_key(key, duration_ms)` | Press and hold a key (for auto-repeat scrolling) |
| `kvm_release_all()` | Force-release all held keys |

### Mouse
| Tool | Description |
|------|-------------|
| `kvm_mouse_move(x, y)` | Move to absolute int16 coordinates |
| `kvm_mouse_move_pct(x_pct, y_pct)` | Move to percentage of screen (0,0 = top-left) |
| `kvm_mouse_click(button?, count?)` | Click at current position |
| `kvm_mouse_scroll(dx?, dy?)` | Scroll the mouse wheel |

### Screenshot
| Tool | Description |
|------|-------------|
| `kvm_screenshot(preview?, max_width?, quality?)` | Capture JPEG frame as MCP image content |
| `kvm_screenshot_to_file(path, preview?, ...)` | Capture and save to disk |

### 🔧 OCR-Enhanced (Tesseract)
| Tool | Description |
|------|-------------|
| `kvm_ocr_screenshot(search_text?, preview?)` | Capture + OCR: returns all text with coordinates |
| `kvm_ocr_click(text, button?, count?, search_area?)` | Find text via OCR and click it — all-in-one |

## 📖 Usage Examples

### Click a button by text name
```python
# One-call: screenshot → OCR → find "Save" → move mouse → click
kvm_ocr_click("Save")
```

### Read all text on screen
```python
# Returns structured JSON with every detected word + coordinates
result = kvm_ocr_screenshot()
# {"width": 1920, "height": 1080, "elements": [
#   {"text": "File", "confidence": 96.3, "x_pct": 5.2, "y_pct": 3.1, ...},
#   {"text": "Edit", "confidence": 95.8, "x_pct": 8.7, "y_pct": 3.1, ...},
#   ...
# ]}
```

### Find specific text and get its coordinates
```python
result = kvm_ocr_screenshot("Submit")
# {"elements": [{"text": "Submit", "confidence": 94.5, "x_pct": 52.3, "y_pct": 87.1, ...}]}
# Then use: kvm_mouse_move_pct(52.3, 87.1) + kvm_mouse_click()
```

### Disambiguate with search area
```python
# If "OK" appears in multiple places, restrict to bottom-right
kvm_ocr_click("OK", search_area="bottom-right")
```

### Traditional screenshot (for vision model analysis)
```python
# Returns MCP image content — agent sees the screenshot directly
kvm_screenshot(preview=True, max_width=1024)
```

## 🏗️ Architecture

```
┌──────────────┐     MCP stdio      ┌─────────────────┐     HTTPS/WSS     ┌──────────┐
│  AI Agent    │ ◄─────────────────► │  glkvm_mcp.py   │ ◄───────────────► │  GLKVM   │
│ (Claude/GPT) │    tool calls       │  (this server)  │   (PiKVM API)     │  Device  │
└──────────────┘                     └─────────────────┘                   └──────────┘
                                            │
                                     Tesseract OCR
                                     (reads screenshot text)
```

The server maintains a persistent WebSocket connection to the GLKVM device for low-latency keyboard/mouse input, and uses HTTP for screenshots and authentication.

## 🔒 Security

- **LAN only** — designed for trusted local networks
- **TLS verification disabled** — the device ships with a self-signed certificate
- **No credentials stored** — password is passed per-session via tool call

## 🐛 Bug Fixes Implemented

This server includes fixes for known GLKVM/PiKVM firmware bugs:
- **Stuck key / double-typing** (firmware ≤ 1.9.0): every character sent as atomic keydown → 25ms → keyup(finish=true)
- **Modifier release order bug** (gl-inet/glkvm #22): modifiers wrap strictly outside the main key
- **Stale key watchdog**: auto-releases any key held >250ms

## 📋 Requirements

- Python ≥ 3.10
- A GL.iNet GLKVM device (firmware 1.9.0+) or PiKVM-compatible device on your LAN
- Tesseract OCR installed on the host machine

## License

MIT
