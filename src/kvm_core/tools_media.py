from __future__ import annotations

import logging
from pathlib import Path

from src.kvm_core.server import mcp
from src.kvm_core.tools_core import _managed_client, _operation_fence

LOG = logging.getLogger("kvm_core.tools")


@mcp.tool(name="comet_media_upload", annotations={"readOnlyHint": False, "destructiveHint": True})
async def comet_media_upload(local_path: str, image_name: str = "", target: str | None = None) -> dict:
    """Upload a local image via raw POST /api/msd/write?image=... (streamed).

    Legacy callers may pass image_name empty to use the local basename.
    """
    async with _operation_fence():
        client = await _managed_client(target)
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
    client = await _managed_client(target)
    return await client.msd_state()


@mcp.tool(name="comet_media_fetch", annotations={"readOnlyHint": False, "destructiveHint": True})
async def comet_media_fetch(url: str, image_name: str, target: str | None = None) -> dict:
    """Ask the Comet to download an image from URL onto MSD storage."""
    async with _operation_fence():
        client = await _managed_client(target)
        return await client.msd_fetch_remote(url, image_name)


@mcp.tool(name="comet_media_mount", annotations={"readOnlyHint": False, "destructiveHint": True})
async def comet_media_mount(
    image_name: str,
    mode: str = "cdrom",
    read_only: bool = True,
    target: str | None = None,
) -> dict:
    """Select an MSD image and connect it to the target."""
    async with _operation_fence():
        client = await _managed_client(target)
        return await client.msd_mount(image_name, mode=mode, read_only=read_only)


@mcp.tool(name="comet_media_unmount", annotations={"readOnlyHint": False, "destructiveHint": True})
async def comet_media_unmount(target: str | None = None) -> dict:
    """Disconnect the virtual media drive from the target."""
    async with _operation_fence():
        client = await _managed_client(target)
        return await client.msd_unmount()


@mcp.tool(name="comet_media_remove", annotations={"readOnlyHint": False, "destructiveHint": True})
async def comet_media_remove(image_name: str, target: str | None = None) -> dict:
    """Delete a stored MSD image."""
    async with _operation_fence():
        client = await _managed_client(target)
        return await client.msd_remove(image_name)


@mcp.tool(name="comet_media_reset", annotations={"readOnlyHint": False, "destructiveHint": True})
async def comet_media_reset(target: str | None = None) -> dict:
    """Reset the MSD subsystem."""
    async with _operation_fence():
        client = await _managed_client(target)
        return await client.msd_reset()
