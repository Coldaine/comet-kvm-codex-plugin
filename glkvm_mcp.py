#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "mcp[cli]>=1.2",
#     "websockets>=12",
#     "httpx>=0.27",
#     "Pillow>=10",
#     "pytesseract>=0.3.13",
# ]
# ///
"""
GLKVM MCP Server
================

Exposes a GL.iNet GLKVM (firmware 1.9.0+, PiKVM-fork) device's keyboard, mouse,
and screenshot capabilities as MCP tools, fully integrated with a stateful
BIOS/KVM sidecar runtime.

Run: `uv run glkvm_mcp.py`
"""

from __future__ import annotations

import logging
from pathlib import Path
from mcp.server.fastmcp import Image
from src.kvm_core.server import mcp
from src.kvm_core.runtime import get_kvm_runtime
import src.bios_sidecar.mcp.server  # registers bios_* tools on the shared mcp instance
from src.bios_sidecar.mcp.server import get_runtime as get_bios_runtime

LOG = logging.getLogger("glkvm_mcp")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Delegate legacy connection tools to the stateful runtime client
def _require_client():
    r = get_kvm_runtime()
    if r.client is None or not r.client.is_connected():
        raise RuntimeError("Not connected. Call kvm_connect first.")
    return r.client

def _safe_screenshot_path(requested_path: str) -> Path:
    requested = Path(requested_path)
    if requested.is_absolute() or ".." in requested.parts:
        raise ValueError("path must be a filename or relative path under the screenshot cache directory")
    root = Path(get_kvm_runtime().capture_mgr.cache_dir).resolve()
    destination = (root / requested).resolve()
    if root != destination and root not in destination.parents:
        raise ValueError("path escapes the screenshot cache directory")
    destination.parent.mkdir(parents=True, exist_ok=True)
    return destination

@mcp.tool(name="kvm_connect", annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True})
async def kvm_connect(host: str, password: str, username: str = "admin") -> dict:
    """Connect to a GLKVM device on LAN and authenticate."""
    r = get_bios_runtime()
    ok = await r.connect_comet(host, password, username)
    return {"connected": ok, "host": r.client.base_url, "message": "ok"}

@mcp.tool(name="kvm_disconnect", annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True})
async def kvm_disconnect() -> dict:
    """Close the WebSocket and HTTP session."""
    r = get_bios_runtime()
    await r.disconnect_comet()
    return {"connected": False, "message": "disconnected"}

@mcp.tool(name="kvm_send_text", annotations={"readOnlyHint": False, "destructiveHint": True})
async def kvm_send_text(text: str, wpm: int = 200) -> dict:
    """Type a string on the remote machine using the bug-fix atomic press patterns."""
    client = _require_client()
    return await client.send_text(text, wpm)

@mcp.tool(name="kvm_send_keys", annotations={"readOnlyHint": False, "destructiveHint": True})
async def kvm_send_keys(combo: str) -> dict:
    """Send a single key chord, e.g. "Ctrl+Alt+Delete", "Escape", "ArrowDown"."""
    client = _require_client()
    return await client.send_combo(combo)

@mcp.tool(name="kvm_hold_key", annotations={"readOnlyHint": False, "destructiveHint": True})
async def kvm_hold_key(key: str, duration_ms: int) -> dict:
    """Press and hold a single key for an explicit duration, then release."""
    client = _require_client()
    return await client.hold_key(key, duration_ms)

@mcp.tool(name="kvm_release_all", annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True})
async def kvm_release_all() -> dict:
    """Force-release every key currently held. Recovery tool."""
    client = _require_client()
    return await client.release_all()

@mcp.tool(name="kvm_mouse_move", annotations={"readOnlyHint": False, "destructiveHint": True})
async def kvm_mouse_move(x: int, y: int) -> dict:
    """Move cursor to absolute coordinates in PiKVM-normalized space."""
    client = _require_client()
    x_pct = (x + 32768) / 65535.0 * 100.0
    y_pct = (y + 32768) / 65535.0 * 100.0
    return await client.mouse_move_pct(x_pct, y_pct)

@mcp.tool(name="kvm_mouse_move_pct", annotations={"readOnlyHint": False, "destructiveHint": True})
async def kvm_mouse_move_pct(x_pct: float, y_pct: float) -> dict:
    """Move cursor to screen percentage coordinates: (0,0)=top-left, (100,100)=bottom-right."""
    client = _require_client()
    return await client.mouse_move_pct(x_pct, y_pct)

@mcp.tool(name="kvm_mouse_click", annotations={"readOnlyHint": False, "destructiveHint": True})
async def kvm_mouse_click(button: str = "left", count: int = 1) -> dict:
    """Clicks named button count times at the current cursor position."""
    client = _require_client()
    return await client.mouse_click(button, count)

@mcp.tool(name="kvm_mouse_scroll", annotations={"readOnlyHint": False, "destructiveHint": True})
async def kvm_mouse_scroll(dx: int = 0, dy: int = 0) -> dict:
    """Scroll mouse wheel delta."""
    client = _require_client()
    return await client.mouse_scroll(dx, dy)

@mcp.tool(name="kvm_screenshot", annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True})
async def kvm_screenshot(preview: bool = True, max_width: int = 1024, quality: int = 60) -> Image:
    """Capture snapshot frame."""
    client = _require_client()
    data = await client.get_screenshot(preview, max_width, quality)
    return Image(data=data, format="jpeg")

@mcp.tool(name="kvm_screenshot_to_file", annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True})
async def kvm_screenshot_to_file(path: str, preview: bool = False, max_width: int = 1920, quality: int = 80) -> dict:
    """Capture snapshot and store under the screenshot cache directory."""
    client = _require_client()
    data = await client.get_screenshot(preview, max_width, quality)
    destination = _safe_screenshot_path(path)
    with open(destination, "wb") as f:
        f.write(data)
    return {"path": str(destination), "bytes": len(data), "mime_type": "image/jpeg"}

@mcp.tool(name="kvm_ocr_screenshot", annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True})
async def kvm_ocr_screenshot(search_text: str = "", preview: bool = False) -> dict:
    """Capture full screenshot and run Tesseract OCR."""
    client = _require_client()
    r = get_kvm_runtime()
    img_bytes = await client.get_screenshot(preview=preview)
    return r.ocr_mgr.run_ocr(img_bytes, search_text)

@mcp.tool(name="kvm_ocr_click", annotations={"readOnlyHint": False, "destructiveHint": True})
async def kvm_ocr_click(text: str, button: str = "left", count: int = 1, search_area: str = "") -> dict:
    """Find text coordinates on screen and mouse click."""
    client = _require_client()
    r = get_kvm_runtime()
    img_bytes = await client.get_screenshot(preview=False)
    ocr = r.ocr_mgr.run_ocr(img_bytes, text)
    if not ocr["elements"]:
        return {"found": False, "text": text, "message": "No matches."}

    elements = ocr["elements"]
    if search_area:
        area_filters = {
            "top-left":     lambda e: e["x_pct"] < 50 and e["y_pct"] < 50,
            "top-right":    lambda e: e["x_pct"] >= 50 and e["y_pct"] < 50,
            "bottom-left":  lambda e: e["x_pct"] < 50 and e["y_pct"] >= 50,
            "bottom-right": lambda e: e["x_pct"] >= 50 and e["y_pct"] >= 50,
        }
        f = area_filters.get(search_area)
        if f:
            filtered = [e for e in elements if f(e)]
            if filtered:
                elements = filtered

    elements.sort(key=lambda e: -e["confidence"])
    best = elements[0]
    await client.mouse_move_pct(best["x_pct"], best["y_pct"])
    await client.mouse_click(button, count)
    return {
        "found": True,
        "text": best["text"],
        "confidence": best["confidence"],
        "x_pct": best["x_pct"],
        "y_pct": best["y_pct"],
        "clicked": True
    }

@mcp.tool(name="kvm_status", annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True})
async def kvm_status() -> dict:
    """Report current active connection status."""
    r = get_kvm_runtime()
    if r.client is None or not r.client.is_connected():
        return {"connected": False, "host": "", "held_keys": [], "ws_open": False}
    return {
        "connected": True,
        "host": r.client.base_url,
        "held_keys": list(r.client.held.keys()),
        "ws_open": r.client.is_connected()
    }


@mcp.tool(name="comet_atx_power", annotations={"readOnlyHint": False, "destructiveHint": True})
async def comet_atx_power(action: str) -> dict:
    """Power on/off/reset the target via ATX board. Action: 'on', 'off', 'reset'."""
    client = _require_client()
    return await client.atx_power(action)

@mcp.tool(name="comet_atx_click", annotations={"readOnlyHint": False, "destructiveHint": True})
async def comet_atx_click(button: str) -> dict:
    """Momentary press of power/reset button ('power' or 'reset', ~200ms pulse)."""
    client = _require_client()
    return await client.atx_click(button)

@mcp.tool(name="comet_sysinfo", annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True})
async def comet_sysinfo() -> dict:
    """Retrieve device metadata: model, firmware version, capabilities."""
    client = _require_client()
    return await client.get_sysinfo()

@mcp.tool(name="comet_msd_upload", annotations={"readOnlyHint": False, "destructiveHint": True})
async def comet_msd_upload(remote_path: str, local_path: str) -> dict:
    """Upload a local file to the Comet's /userdata/media/ partition for on-device persistence."""
    client = _require_client()
    try:
        with open(local_path, "rb") as f:
            data = f.read()
    except Exception as e:
        raise ValueError(f"Failed to read local file {local_path}: {e}")
    return await client.msd_upload(remote_path, data)

if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore", message="Unverified HTTPS request")
    mcp.run()
