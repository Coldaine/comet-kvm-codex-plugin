from __future__ import annotations

import logging

from src.kvm_core.server import mcp
from src.kvm_core.tools_core import _require_client

LOG = logging.getLogger("kvm_core.tools")


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
