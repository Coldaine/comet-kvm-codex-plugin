from __future__ import annotations

import asyncio
import os

import pytest

# Talk to the real Comet whenever credentials are available.
# Skip only when there is no password (e.g. default GitHub CI without Doppler).
# Force with RUN_LIVE_COMET_SMOKE=1 even if you want an explicit gate; force-off with
# RUN_LIVE_COMET_SMOKE=0.
_FORCE = os.environ.get("RUN_LIVE_COMET_SMOKE")
_HAS_PASSWORD = bool(
    os.environ.get("COMET_PASSWORD") or os.environ.get("GLCOMET_ADMIN_PASSWORD")
)

if _FORCE == "0":
    pytest.skip("RUN_LIVE_COMET_SMOKE=0 disables live Comet checks", allow_module_level=True)
elif _FORCE != "1" and not _HAS_PASSWORD:
    pytest.skip(
        "no COMET_PASSWORD/GLCOMET_ADMIN_PASSWORD — live Comet smoke not attempted",
        allow_module_level=True,
    )


def test_live_comet_auth_sysinfo_and_screenshot_readonly():
    """Read-only: login, sysinfo, one JPEG snapshot. No ATX/MSD/HID mutation."""
    from src.kvm_core.comet.client import CometClient

    host = os.environ.get("COMET_HOST", "192.168.0.126")
    username = os.environ.get("COMET_USERNAME", "admin")
    password = os.environ.get("COMET_PASSWORD") or os.environ.get("GLCOMET_ADMIN_PASSWORD")
    if not password:
        pytest.fail("COMET_PASSWORD or GLCOMET_ADMIN_PASSWORD is required")

    async def run() -> None:
        client = CometClient(host=host, username=username, password=password)
        try:
            assert await client.connect() is True
            sysinfo = await client.get_sysinfo()
            assert isinstance(sysinfo, dict)
            frame = await client.get_screenshot(preview=True, max_width=320, quality=40)
            assert frame.startswith(b"\xff\xd8")
        finally:
            await client.disconnect()

    asyncio.run(asyncio.wait_for(run(), timeout=30))
