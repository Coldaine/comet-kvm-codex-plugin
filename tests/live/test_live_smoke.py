from __future__ import annotations

import asyncio
import os
import socket
import time
from urllib.parse import urlparse

import pytest

from src.kvm_core.doppler_credentials import (
    DopplerAuthError,
    _doppler_get_plain,
    doppler_project_config,
    resolve_comet_password,
)

# Always fetch from Doppler CLI. Skip only when Doppler is missing/unauthenticated
# (e.g. GitHub-hosted runners without CLI login). Force-off: RUN_LIVE_COMET_SMOKE=0.
# Force-on (fail instead of skip when host down): RUN_LIVE_COMET_SMOKE=1.
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


def resolve_live_host() -> str:
    """Prefer COMET_HOST env, then Doppler COMET_HOST, then LAN default."""
    env_host = (os.environ.get("COMET_HOST") or "").strip()
    if env_host:
        return env_host
    project, config = doppler_project_config()
    try:
        from_doppler = _doppler_get_plain("COMET_HOST", project, config)
    except DopplerAuthError:
        from_doppler = None
    return (from_doppler or "192.168.0.126").strip()


def resolve_live_username() -> str:
    env_user = (os.environ.get("COMET_USERNAME") or "").strip()
    if env_user:
        return env_user
    project, config = doppler_project_config()
    try:
        from_doppler = _doppler_get_plain("COMET_ADMIN_USERNAME", project, config)
    except DopplerAuthError:
        from_doppler = None
    return (from_doppler or "admin").strip()


def _tcp_host_port(host: str, default_port: int = 443) -> tuple[str, int]:
    if "://" in host:
        parsed = urlparse(host)
        return parsed.hostname or host, parsed.port or default_port
    if ":" in host and host.count(":") == 1 and not host.startswith("["):
        name, port_s = host.rsplit(":", 1)
        if port_s.isdigit():
            return name, int(port_s)
    return host, default_port


def require_comet_reachable(host: str, timeout: float = 3.0) -> None:
    """Skip (or fail if forced) when the Comet TCP port is unreachable."""
    name, port = _tcp_host_port(host)
    try:
        with socket.create_connection((name, port), timeout=timeout):
            return
    except OSError as exc:
        msg = f"Comet host {name}:{port} unreachable ({exc})"
        if _FORCE == "1":
            pytest.fail(msg)
        pytest.skip(msg)


def _run(coro, timeout: float = 45.0):
    return asyncio.run(asyncio.wait_for(coro, timeout=timeout))


def test_live_comet_auth_sysinfo_and_screenshot_readonly():
    """Read-only: login, sysinfo, one JPEG snapshot. No ATX/MSD/HID mutation."""
    from src.kvm_core.comet.client import CometClient

    host = resolve_live_host()
    require_comet_reachable(host)
    password = resolve_comet_password(require=True)

    async def run() -> None:
        client = CometClient(host=host, username=resolve_live_username(), password=password)
        try:
            assert await client.connect() is True
            sysinfo = await client.get_sysinfo()
            assert isinstance(sysinfo, dict)
            frame = await client.get_screenshot(preview=True, max_width=320, quality=40)
            assert frame.startswith(b"\xff\xd8")
        finally:
            await client.disconnect()

    _run(run(), timeout=30)


def test_live_comet_capabilities_and_readonly_subsystem_state():
    """Lane A: capability profile + read-only ATX/MSD state."""
    from src.kvm_core.comet.client import CometClient

    host = resolve_live_host()
    require_comet_reachable(host)
    password = resolve_comet_password(require=True)

    async def run() -> None:
        client = CometClient(host=host, username=resolve_live_username(), password=password)
        try:
            assert await client.connect() is True
            caps = client.capabilities or await client.discover_capabilities()
            assert isinstance(caps, dict)
            assert "features" in caps or "error" in caps
            if "features" in caps:
                assert isinstance(caps["features"], dict)

            atx = await client.atx_state()
            assert isinstance(atx, dict)

            msd = await client.msd_state()
            assert isinstance(msd, dict)
        finally:
            await client.disconnect()

    _run(run(), timeout=45)


def test_live_comet_websocket_pong_health():
    """Lane A: WS receiver/pinger should record a pong while connected."""
    from src.kvm_core.comet.client import CometClient

    host = resolve_live_host()
    require_comet_reachable(host)
    password = resolve_comet_password(require=True)

    async def run() -> None:
        client = CometClient(host=host, username=resolve_live_username(), password=password)
        try:
            assert await client.connect() is True
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline and client.last_pong_at is None:
                await asyncio.sleep(0.25)
            assert client.is_connected() is True
            assert client.last_pong_at is not None, "expected WS pong within 5s"
            assert client._ws_healthy is True
        finally:
            await client.disconnect()

    _run(run(), timeout=30)
