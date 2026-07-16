from __future__ import annotations

import asyncio
import os

import pytest

from src.kvm_core.doppler_credentials import DopplerAuthError, resolve_comet_password

# Always fetch from Doppler CLI. Skip only when Doppler is missing/unauthenticated
# (e.g. GitHub-hosted runners without CLI login). Force-off: RUN_LIVE_COMET_SMOKE=0.
_FORCE = os.environ.get("RUN_LIVE_COMET_SMOKE")
_PASSWORD: str | None = None
_SKIP_REASON: str | None = None

if _FORCE == "0":
    _SKIP_REASON = "RUN_LIVE_COMET_SMOKE=0 disables live Comet checks"
else:
    try:
        _PASSWORD = resolve_comet_password(require=True)
    except DopplerAuthError as exc:
        _SKIP_REASON = str(exc)

if _SKIP_REASON:
    pytest.skip(_SKIP_REASON, allow_module_level=True)


def test_live_comet_auth_sysinfo_and_screenshot_readonly():
    """Read-only: login, sysinfo, one JPEG snapshot. No ATX/MSD/HID mutation."""
    from src.kvm_core.comet.client import CometClient

    host = os.environ.get("COMET_HOST", "192.168.0.126")
    username = os.environ.get("COMET_USERNAME", "admin")
    password = resolve_comet_password(require=True)

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
