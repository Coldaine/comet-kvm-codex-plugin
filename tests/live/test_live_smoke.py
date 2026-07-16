from __future__ import annotations

import asyncio
import os

import pytest

from tests.live.doppler_env import resolve_comet_password

# Talk to the real Comet whenever credentials are available (env or Doppler CLI).
# Skip only when neither env nor Doppler can supply a password (e.g. GitHub CI
# without DOPPLER_TOKEN / CLI login). Force-off with RUN_LIVE_COMET_SMOKE=0.
_FORCE = os.environ.get("RUN_LIVE_COMET_SMOKE")
_PASSWORD = None if _FORCE == "0" else resolve_comet_password()

if _FORCE == "0":
    pytest.skip("RUN_LIVE_COMET_SMOKE=0 disables live Comet checks", allow_module_level=True)
elif not _PASSWORD:
    pytest.skip(
        "no Comet password in env or Doppler (secrets_managment/dev) — live smoke not attempted",
        allow_module_level=True,
    )


def test_live_comet_auth_sysinfo_and_screenshot_readonly():
    """Read-only: login, sysinfo, one JPEG snapshot. No ATX/MSD/HID mutation."""
    from src.kvm_core.comet.client import CometClient

    host = os.environ.get("COMET_HOST", "192.168.0.126")
    username = os.environ.get("COMET_USERNAME", "admin")
    password = resolve_comet_password()
    if not password:
        pytest.fail("COMET_PASSWORD could not be resolved from env or Doppler")

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
