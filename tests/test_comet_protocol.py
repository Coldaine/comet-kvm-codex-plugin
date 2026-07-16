from __future__ import annotations

import asyncio
import time
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest

from src.kvm_core.comet.client import CometClient, HeldKey
from src.kvm_core.runtime import KVMRuntime
from tests.local_services import CometProtocolService


def run(coro):
    return asyncio.run(coro)


async def wait_until(predicate, timeout: float = 1.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.005)
    raise AssertionError("condition was not met before timeout")


def test_real_protocol_login_websocket_capabilities_and_hid_contract():
    async def scenario() -> tuple[CometProtocolService, dict]:
        async with CometProtocolService() as service:
            client = CometClient(
                service.base_url,
                username="admin",
                password="secret",
                verify_ssl=False,
            )
            client.ws_ping_period = 0.01
            try:
                assert await client.connect() is True
                await wait_until(lambda: client.last_pong_at is not None)
                await wait_until(lambda: "atx_state" in client.server_state)
                result = await client.send_combo("Ctrl+Alt+Delete")
                await wait_until(
                    lambda: sum(1 for row in service.ws_messages if row.get("event_type") == "key") >= 6
                )
                assert client.capabilities["features"]["legacy_server_ocr"] is True
                assert client.server_state["atx_state"]["enabled"] is True
            finally:
                await client.disconnect()
            return service, result

    service, result = run(scenario())
    login = next(row for row in service.requests if row["path"] == "/api/auth/login")
    assert parse_qs(login["body"].decode()) == {
        "user": ["admin"],
        "passwd": ["secret"],
        "expire": ["0"],
    }
    assert service.ws_query == {"stream": "true"}
    assert service.ws_headers["Token"] == "token-123"
    assert "auth_token=token-123" in service.ws_headers["Cookie"]
    assert result == {
        "sent": "Ctrl+Alt+Delete",
        "modifiers": ["ControlLeft", "AltLeft"],
        "key": "Delete",
    }
    key_messages = [row for row in service.ws_messages if row["event_type"] == "key"]
    assert key_messages == [
        {"event_type": "key", "event": {"key": "ControlLeft", "state": True, "finish": False}},
        {"event_type": "key", "event": {"key": "AltLeft", "state": True, "finish": False}},
        {"event_type": "key", "event": {"key": "Delete", "state": True, "finish": False}},
        {"event_type": "key", "event": {"key": "Delete", "state": False, "finish": True}},
        {"event_type": "key", "event": {"key": "AltLeft", "state": False, "finish": True}},
        {"event_type": "key", "event": {"key": "ControlLeft", "state": False, "finish": True}},
    ]
    assert any(row["path"] == "/api/auth/logout" for row in service.requests)


def test_real_login_without_auth_cookie_fails_closed():
    async def scenario() -> None:
        async with CometProtocolService(issue_auth_cookie=False) as service:
            client = CometClient(service.base_url, password="secret")
            with pytest.raises(RuntimeError, match="no auth_token"):
                await client.connect()
            assert client.http is None
            assert client.auth_token is None

    run(scenario())


def test_watchdog_releases_only_stale_unprotected_keys_over_real_websocket():
    async def scenario() -> list[dict]:
        async with CometProtocolService() as service:
            client = CometClient(service.base_url, password="secret")
            client.watchdog_period = 0.005
            client.stale_s = 0.005
            try:
                await client.connect()
                client.held["KeyA"] = HeldKey(pressed_at=0.0, watchdog_protected=False)
                client.held["Delete"] = HeldKey(
                    pressed_at=time.monotonic(),
                    release_deadline=time.monotonic() + 10,
                    watchdog_protected=True,
                )
                await wait_until(lambda: "KeyA" not in client.held)
                await asyncio.sleep(0.02)
                assert "Delete" in client.held
            finally:
                client.held.pop("Delete", None)
                await client.disconnect()
            return service.ws_messages

    messages = run(scenario())
    stale_releases = [
        row for row in messages
        if row.get("event_type") == "key" and row["event"].get("key") == "KeyA"
    ]
    assert stale_releases == [
        {"event_type": "key", "event": {"key": "KeyA", "state": False, "finish": True}}
    ]


def test_atx_query_contract_and_board_error_use_real_http():
    async def scenario() -> tuple[list[dict], dict]:
        async with CometProtocolService() as service:
            client = CometClient(service.base_url)
            client.http = httpx.AsyncClient()
            try:
                result = await client.atx_power("reset", wait=True)
                await client.atx_click("power_long", wait=False)
                service.respond("/api/atx/power", 500, "ATX board not connected")
                with pytest.raises(RuntimeError, match="ATX board not detected"):
                    await client.atx_power("reset")
            finally:
                await client.http.aclose()
            return service.requests, result

    requests, result = run(scenario())
    atx = [row for row in requests if row["path"] == "/api/atx/power"]
    assert atx[0]["query"] == {"action": "reset_hard", "wait": "true"}
    click = next(row for row in requests if row["path"] == "/api/atx/click")
    assert click["query"] == {"button": "power_long", "wait": "false"}
    assert result["action"] == "reset_hard"


def test_msd_upload_and_mount_contract_use_real_http(tmp_path: Path):
    media = tmp_path / "proxmox.iso"
    media.write_bytes(b"ISO-BYTES-123")

    async def scenario() -> tuple[list[dict], dict]:
        async with CometProtocolService() as service:
            client = CometClient(service.base_url)
            client.http = httpx.AsyncClient()
            client.auth_token = "token-123"
            try:
                upload = await client.msd_upload_file(str(media), "proxmox.iso")
                await client.msd_mount("proxmox.iso", mode="cdrom", read_only=True)
                with pytest.raises(ValueError, match="Unsupported MSD mode"):
                    await client.msd_mount("proxmox.iso", mode="tape")
            finally:
                await client.http.aclose()
            return service.requests, upload

    requests, upload = run(scenario())
    write = next(row for row in requests if row["path"] == "/api/msd/write")
    assert write["query"] == {"image": "proxmox.iso"}
    assert write["body"] == b"ISO-BYTES-123"
    assert write["headers"]["Content-Length"] == str(len(b"ISO-BYTES-123"))
    assert write["headers"]["Content-Type"] == "application/octet-stream"
    mount = [row for row in requests if row["path"].startswith("/api/msd/set_")]
    assert [(row["path"], row["query"]) for row in mount] == [
        ("/api/msd/set_params", {"image": "proxmox.iso", "cdrom": "true", "rw": "false"}),
        ("/api/msd/set_connected", {"connected": "true"}),
    ]
    assert upload["bytes"] == len(b"ISO-BYTES-123")


def test_multi_target_runtime_keeps_sessions_independent():
    async def scenario() -> tuple[list[dict], str]:
        async with CometProtocolService() as first, CometProtocolService() as second:
            runtime = KVMRuntime()
            try:
                await runtime.connect(first.base_url, password="secret", target="alpha")
                await runtime.connect(
                    second.base_url,
                    password="secret",
                    target="beta",
                    select=False,
                )
                rows = runtime.list_targets()
                assert runtime.get_client("alpha").base_url == first.base_url
                assert runtime.get_client("beta").base_url == second.base_url
                selected = runtime.select_target("beta")
                return rows, selected
            finally:
                await runtime.disconnect()

    rows, selected = run(scenario())
    assert selected == "beta"
    assert {row["target"] for row in rows} == {"alpha", "beta"}
    assert next(row for row in rows if row["target"] == "alpha")["selected"] is True
