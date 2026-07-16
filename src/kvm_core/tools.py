from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from mcp.server.fastmcp import Image

from src.kvm_core.runtime import get_kvm_runtime
from src.kvm_core.server import mcp
from src.kvm_core.ocr import validate_psm

LOG = logging.getLogger("kvm_core.tools")


def _require_client(target: str | None = None):
    return get_kvm_runtime().get_client(target)


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


def resolve_screenshot_ref(screenshot_ref: str) -> Path:
    """Resolve an opaque screenshot id/name strictly under the screenshot cache."""
    requested = Path(screenshot_ref)
    if requested.is_absolute() or ".." in requested.parts:
        raise ValueError("invalid screenshot reference")
    root = Path(get_kvm_runtime().capture_mgr.cache_dir).resolve()
    candidates = [
        (root / requested).resolve(),
        (root / f"{screenshot_ref}.jpg").resolve(),
        (root / requested.name).resolve(),
    ]
    for candidate in candidates:
        if root != candidate and root not in candidate.parents:
            continue
        if candidate.is_file() and candidate.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
            return candidate
    raise FileNotFoundError(f"Screenshot ref not found in cache: {screenshot_ref}")


@mcp.tool(name="kvm_connect", annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True})
async def kvm_connect(
    host: str,
    password: str | None = None,
    username: str = "admin",
    target: str = "default",
) -> dict:
    """Connect to a GLKVM device on LAN and authenticate.

    When no password is supplied, use a credential injected into this MCP
    process instead of exposing the credential in a tool call.
    Optional target id enables multi-Comet sessions.
    """
    if password is None:
        password = os.environ.get("COMET_PASSWORD") or os.environ.get("GLCOMET_ADMIN_PASSWORD")
    if not password:
        raise ValueError(
            "No Comet password was provided. Pass password explicitly or inject "
            "COMET_PASSWORD/GLCOMET_ADMIN_PASSWORD into the MCP process."
        )
    r = get_kvm_runtime()
    ok = await r.connect(host=host, username=username, password=password, target=target)
    client = r.get_client(target)
    return {
        "connected": ok,
        "host": client.base_url,
        "target": target,
        "capabilities": client.capabilities,
        "message": "ok",
    }


@mcp.tool(name="kvm_disconnect", annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True})
async def kvm_disconnect(target: str | None = None) -> dict:
    """Close WebSocket/HTTP session for one target, or all targets when omitted."""
    r = get_kvm_runtime()
    await r.disconnect(target)
    return {"connected": False, "target": target, "targets": r.list_targets(), "message": "disconnected"}


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
async def kvm_ocr_screenshot(search_text: str = "", preview: bool = False, psm: int = 3) -> dict:
    """Capture a screenshot and return ordered screen text plus word coordinates.

    Use psm=6 for a full-screen terminal or other single text block.
    """
    client = _require_client()
    r = get_kvm_runtime()
    img_bytes = await client.get_screenshot(preview=preview)
    return await asyncio.to_thread(r.ocr_mgr.run_ocr, img_bytes, search_text, psm)


def _ocr_crop(left: int, top: int, right: int, bottom: int) -> tuple[int, int, int, int] | None:
    values = (left, top, right, bottom)
    if all(value < 0 for value in values):
        return None
    if right >= 0 and left >= right:
        raise ValueError("right must be greater than left")
    if bottom >= 0 and top >= bottom:
        raise ValueError("bottom must be greater than top")
    return values


@mcp.tool(name="kvm_ocr_status", annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True})
async def kvm_ocr_status() -> dict:
    """Report native Comet OCR and host Tesseract availability."""
    client = _require_client()
    r = get_kvm_runtime()
    try:
        device = await client.get_ocr_state(refresh=True)
    except Exception as exc:
        LOG.warning("Native OCR capability probe failed: %s", type(exc).__name__)
        device = {"enabled": False, "error": "capability probe failed"}
    host = r.ocr_mgr.get_status()
    if device.get("enabled"):
        recommended = "comet-native"
    elif host.get("available"):
        recommended = "host-tesseract"
    else:
        recommended = "unavailable"
    return {
        "device": device,
        "host": host,
        "recommended_text_engine": recommended,
    }


@mcp.tool(name="kvm_ocr_text", annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True})
async def kvm_ocr_text(
    psm: int = 6,
    languages: str = "",
    prefer_native: bool = True,
    left: int = -1,
    top: int = -1,
    right: int = -1,
    bottom: int = -1,
) -> dict:
    """Return visible screen text through native OCR when available, else host Tesseract.

    This text-only path preserves terminal spacing and avoids word-box work. Crop
    coordinates are pixels; leave all four at -1 for the full frame.
    """
    client = _require_client()
    r = get_kvm_runtime()
    crop = _ocr_crop(left, top, right, bottom)
    device_state = None
    fallback_reason = "native OCR not requested"

    if prefer_native:
        try:
            device_state = await client.get_ocr_state()
            if device_state.get("enabled"):
                text = (await client.get_native_ocr_text(languages, crop)).rstrip()
                return {
                    "engine": f"comet-native:{device_state.get('engine', 'unknown')}",
                    "text": text,
                    "lines": text.splitlines(),
                    "crop": list(crop) if crop else None,
                    "device": device_state,
                }
            fallback_reason = "device OCR is disabled"
        except Exception as exc:
            LOG.warning("Native OCR read failed; using host fallback: %s", type(exc).__name__)
            fallback_reason = "native OCR request failed"

    validate_psm(psm)
    image_bytes = await client.get_screenshot(preview=False)
    host = await asyncio.to_thread(r.ocr_mgr.run_text_ocr, image_bytes, psm, languages, crop)
    if "error" in host:
        raise RuntimeError(host["error"])
    host.update({
        "engine": "host-tesseract",
        "crop": list(crop) if crop else None,
        "device": device_state,
        "fallback_reason": fallback_reason,
    })
    return host


@mcp.tool(name="kvm_ocr_click", annotations={"readOnlyHint": False, "destructiveHint": True})
async def kvm_ocr_click(text: str, button: str = "left", count: int = 1, search_area: str = "") -> dict:
    """Find text coordinates on screen and mouse click."""
    client = _require_client()
    r = get_kvm_runtime()
    img_bytes = await client.get_screenshot(preview=False)
    ocr = await asyncio.to_thread(r.ocr_mgr.run_ocr, img_bytes, text)
    if "error" in ocr:
        raise RuntimeError(ocr["error"])
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
async def kvm_status(target: str | None = None) -> dict:
    """Report current active connection status."""
    r = get_kvm_runtime()
    try:
        client = r.get_client(target)
    except RuntimeError:
        return {
            "connected": False,
            "host": "",
            "held_keys": [],
            "ws_open": False,
            "selected_target": r.selected_target,
            "targets": r.list_targets(),
        }
    return {
        "connected": True,
        "host": client.base_url,
        "target": client.target_id,
        "held_keys": list(client.held.keys()),
        "ws_open": client.is_connected(),
        "last_server_event_at": client.last_server_event_at,
        "last_pong_at": client.last_pong_at,
        "server_state_keys": sorted(client.server_state.keys()),
        "capabilities": client.capabilities,
        "selected_target": r.selected_target,
        "targets": r.list_targets(),
    }


@mcp.tool(name="kvm_select_target", annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True})
async def kvm_select_target(target: str) -> dict:
    """Select the default Comet target for subsequent tool calls."""
    r = get_kvm_runtime()
    selected = r.select_target(target)
    return {"selected_target": selected, "targets": r.list_targets()}


@mcp.tool(name="comet_power_state", annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True})
async def comet_power_state(target: str | None = None) -> dict:
    """Read ATX power/LED state via GET /api/atx."""
    client = _require_client(target)
    return await client.atx_state()


@mcp.tool(name="comet_atx_power", annotations={"readOnlyHint": False, "destructiveHint": True})
async def comet_atx_power(action: str, wait: bool = True, target: str | None = None) -> dict:
    """ATX power action via query params. Actions: on, off, off_hard, reset_hard (aliases: reset, force_off)."""
    client = _require_client(target)
    return await client.atx_power(action, wait=wait)


@mcp.tool(name="comet_atx_click", annotations={"readOnlyHint": False, "destructiveHint": True})
async def comet_atx_click(button: str, wait: bool = True, target: str | None = None) -> dict:
    """Momentary ATX button press: power, power_long, or reset."""
    client = _require_client(target)
    return await client.atx_click(button, wait=wait)


@mcp.tool(name="comet_sysinfo", annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True})
async def comet_sysinfo(target: str | None = None) -> dict:
    """Retrieve device metadata: model, firmware version, capabilities."""
    client = _require_client(target)
    return await client.get_sysinfo()


@mcp.tool(name="comet_capabilities", annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True})
async def comet_capabilities(refresh: bool = False, target: str | None = None) -> dict:
    """Return connect-time capability profile (model/firmware/features)."""
    client = _require_client(target)
    if refresh or not client.capabilities:
        return await client.discover_capabilities()
    return client.capabilities


@mcp.tool(name="comet_msd_upload", annotations={"readOnlyHint": False, "destructiveHint": True})
async def comet_msd_upload(local_path: str, image_name: str = "", target: str | None = None) -> dict:
    """Upload a local image via raw POST /api/msd/write?image=... (streamed).

    Legacy callers may pass image_name empty to use the local basename.
    """
    client = _require_client(target)
    path = Path(local_path)
    if not path.is_file():
        err = FileNotFoundError(local_path)
        raise ValueError(f"Failed to read local file {local_path}: {err}") from err
    try:
        return await client.msd_upload_file(local_path, image_name or None)
    except FileNotFoundError as e:
        raise ValueError(f"Failed to read local file {local_path}: {e}") from e


@mcp.tool(name="comet_media_state", annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True})
async def comet_media_state(target: str | None = None) -> dict:
    """Return virtual-media / MSD subsystem state."""
    return await _require_client(target).msd_state()


@mcp.tool(name="comet_media_upload", annotations={"readOnlyHint": False, "destructiveHint": True})
async def comet_media_upload(local_path: str, image_name: str = "", target: str | None = None) -> dict:
    """Stream a local ISO/image onto the Comet MSD storage."""
    return await comet_msd_upload(local_path, image_name, target)


@mcp.tool(name="comet_media_fetch", annotations={"readOnlyHint": False, "destructiveHint": True})
async def comet_media_fetch(url: str, image_name: str, target: str | None = None) -> dict:
    """Ask the Comet to download an image from URL onto MSD storage."""
    return await _require_client(target).msd_fetch_remote(url, image_name)


@mcp.tool(name="comet_media_mount", annotations={"readOnlyHint": False, "destructiveHint": True})
async def comet_media_mount(
    image_name: str,
    mode: str = "cdrom",
    read_only: bool = True,
    target: str | None = None,
) -> dict:
    """Select an MSD image and connect it to the target."""
    return await _require_client(target).msd_mount(image_name, mode=mode, read_only=read_only)


@mcp.tool(name="comet_media_unmount", annotations={"readOnlyHint": False, "destructiveHint": True})
async def comet_media_unmount(target: str | None = None) -> dict:
    """Disconnect the virtual media drive from the target."""
    return await _require_client(target).msd_unmount()


@mcp.tool(name="comet_media_remove", annotations={"readOnlyHint": False, "destructiveHint": True})
async def comet_media_remove(image_name: str, target: str | None = None) -> dict:
    """Delete a stored MSD image."""
    return await _require_client(target).msd_remove(image_name)


@mcp.tool(name="comet_media_reset", annotations={"readOnlyHint": False, "destructiveHint": True})
async def comet_media_reset(target: str | None = None) -> dict:
    """Reset the MSD subsystem."""
    return await _require_client(target).msd_reset()


@mcp.tool(name="comet_wol_list", annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True})
async def comet_wol_list(target: str | None = None) -> dict:
    """List Wake-on-LAN entries known to the Comet."""
    return await _require_client(target).wol_list()


@mcp.tool(name="comet_wol_scan", annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True})
async def comet_wol_scan(target: str | None = None) -> dict:
    """ARP-scan the local segment for WOL candidates."""
    return await _require_client(target).wol_scan()


@mcp.tool(name="comet_wol_wake", annotations={"readOnlyHint": False, "destructiveHint": True})
async def comet_wol_wake(mac: str, target: str | None = None) -> dict:
    """Send a Wake-on-LAN packet for the given MAC."""
    return await _require_client(target).wol_wake(mac)


@mcp.tool(name="comet_streamer_state", annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True})
async def comet_streamer_state(target: str | None = None) -> dict:
    """Return HDMI streamer state and parameters."""
    return await _require_client(target).streamer_state()


@mcp.tool(name="comet_streamer_set_params", annotations={"readOnlyHint": False, "destructiveHint": False})
async def comet_streamer_set_params(
    quality: int | None = None,
    desired_fps: int | None = None,
    resolution: str | None = None,
    target: str | None = None,
) -> dict:
    """Update stream quality/fps/resolution when supported."""
    return await _require_client(target).streamer_set_params(
        quality=quality,
        desired_fps=desired_fps,
        resolution=resolution,
    )


@mcp.tool(name="comet_recorder_state", annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True})
async def comet_recorder_state(target: str | None = None) -> dict:
    """Return recorder subsystem state."""
    return await _require_client(target).recorder_state()


@mcp.tool(name="comet_recorder_start", annotations={"readOnlyHint": False, "destructiveHint": True})
async def comet_recorder_start(target: str | None = None) -> dict:
    """Start H.264 console recording on the Comet."""
    return await _require_client(target).recorder_start()


@mcp.tool(name="comet_recorder_stop", annotations={"readOnlyHint": False, "destructiveHint": True})
async def comet_recorder_stop(target: str | None = None) -> dict:
    """Stop console recording."""
    return await _require_client(target).recorder_stop()


@mcp.tool(name="comet_metrics", annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True})
async def comet_metrics(target: str | None = None) -> dict:
    """Fetch Prometheus metrics text from the Comet."""
    text = await _require_client(target).prometheus_metrics()
    return {"metrics": text, "bytes": len(text.encode("utf-8"))}


@mcp.tool(name="comet_tailscale_status", annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True})
async def comet_tailscale_status(target: str | None = None) -> dict:
    """Read Tailscale status from the Comet appliance."""
    return await _require_client(target).tailscale_status()


@mcp.tool(name="comet_redfish_power", annotations={"readOnlyHint": False, "destructiveHint": True})
async def comet_redfish_power(reset_type: str, target: str | None = None) -> dict:
    """Issue a Redfish ComputerSystem.Reset (On, ForceOff, ForceRestart, PushPowerButton, ...)."""
    return await _require_client(target).redfish_reset(reset_type)

# Deprecated aliases remain registered for backwards compatibility. They are
# deliberately thin delegates so their behavior stays identical to kvm_*.
@mcp.tool(name="comet_raw_send_text", annotations={"readOnlyHint": False, "destructiveHint": True})
async def comet_raw_send_text(text: str, wpm: int = 200) -> dict:
    """Deprecated alias of kvm_send_text."""
    return await kvm_send_text(text, wpm)


@mcp.tool(name="comet_raw_send_keys", annotations={"readOnlyHint": False, "destructiveHint": True})
async def comet_raw_send_keys(combo: str) -> dict:
    """Deprecated alias of kvm_send_keys."""
    return await kvm_send_keys(combo)


@mcp.tool(name="comet_raw_hold_key", annotations={"readOnlyHint": False, "destructiveHint": True})
async def comet_raw_hold_key(key: str, duration_ms: int) -> dict:
    """Deprecated alias of kvm_hold_key."""
    return await kvm_hold_key(key, duration_ms)


@mcp.tool(name="comet_raw_release_all", annotations={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": True})
async def comet_raw_release_all() -> dict:
    """Deprecated alias of kvm_release_all."""
    return await kvm_release_all()


@mcp.tool(name="comet_raw_mouse_move", annotations={"readOnlyHint": False, "destructiveHint": True})
async def comet_raw_mouse_move(x: int, y: int) -> dict:
    """Deprecated alias of kvm_mouse_move."""
    return await kvm_mouse_move(x, y)


@mcp.tool(name="comet_raw_mouse_move_pct", annotations={"readOnlyHint": False, "destructiveHint": True})
async def comet_raw_mouse_move_pct(x_pct: float, y_pct: float) -> dict:
    """Deprecated alias of kvm_mouse_move_pct."""
    return await kvm_mouse_move_pct(x_pct, y_pct)


@mcp.tool(name="comet_raw_mouse_click", annotations={"readOnlyHint": False, "destructiveHint": True})
async def comet_raw_mouse_click(button: str = "left", count: int = 1) -> dict:
    """Deprecated alias of kvm_mouse_click."""
    return await kvm_mouse_click(button, count)


@mcp.tool(name="comet_raw_mouse_scroll", annotations={"readOnlyHint": False, "destructiveHint": True})
async def comet_raw_mouse_scroll(dx: int = 0, dy: int = 0) -> dict:
    """Deprecated alias of kvm_mouse_scroll."""
    return await kvm_mouse_scroll(dx, dy)


@mcp.tool(name="comet_raw_screenshot", annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True})
async def comet_raw_screenshot(preview: bool = True, max_width: int = 1024, quality: int = 60) -> Image:
    """Deprecated alias of kvm_screenshot."""
    return await kvm_screenshot(preview, max_width, quality)


@mcp.tool(name="comet_raw_status", annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True})
async def comet_raw_status() -> dict:
    """Deprecated alias of kvm_status."""
    return await kvm_status()
