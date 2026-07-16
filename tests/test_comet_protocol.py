from __future__ import annotations

import asyncio
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from src.kvm_core.comet import client as comet_client
from src.kvm_core.comet.client import CometClient, HeldKey


class FakeResponse:
    def __init__(
        self,
        status_code: int = 200,
        text: str = "ok",
        *,
        json_data: dict | None = None,
        headers: dict | None = None,
    ) -> None:
        self.status_code = status_code
        self.text = text if json_data is None else json.dumps(json_data)
        self.is_success = status_code < 400
        self.headers = headers or ({"content-type": "application/json"} if json_data is not None else {})
        self._json = json_data

    def raise_for_status(self) -> None:
        if not self.is_success:
            raise httpx.HTTPStatusError(
                "request failed",
                request=httpx.Request("POST", "https://comet.invalid"),
                response=httpx.Response(self.status_code, text=self.text),
            )

    def json(self) -> dict:
        if self._json is not None:
            return self._json
        return json.loads(self.text)


class FakeCookies:
    def __init__(self, token: str | None) -> None:
        self.token = token

    def get(self, name: str) -> str | None:
        if name == "auth_token":
            return self.token
        return None


class FakeHTTPClient:
    def __init__(self, token: str | None = "token-123") -> None:
        self.cookies = FakeCookies(token)
        self.headers: dict[str, str] = {}
        self.post_calls: list[dict[str, object]] = []
        self.get_calls: list[dict[str, object]] = []
        self.closed = False

    async def post(self, url: str, **kwargs: object) -> FakeResponse:
        self.post_calls.append({"url": url, **kwargs})
        if url.endswith("/api/auth/logout"):
            return FakeResponse(json_data={"ok": True, "result": {}})
        return FakeResponse(json_data={"ok": True, "result": {}})

    async def get(self, url: str, **kwargs: object) -> FakeResponse:
        self.get_calls.append({"url": url, **kwargs})
        return FakeResponse(json_data={"ok": True, "result": {}})

    async def aclose(self) -> None:
        self.closed = True


class FakeWebSocket:
    def __init__(self, fail_on_send: bool = False) -> None:
        self.sent: list[str] = []
        self.closed = False
        self.fail_on_send = fail_on_send
        self._recv_queue: asyncio.Queue[str | bytes] = asyncio.Queue()

    async def send(self, payload: str) -> None:
        self.sent.append(payload)
        if self.fail_on_send:
            raise RuntimeError("send failed")

    async def recv(self) -> str | bytes:
        return await self._recv_queue.get()

    async def close(self) -> None:
        self.closed = True
        await self._recv_queue.put('{"event_type":"kickout","event":{}}')


def _run(coro):
    return asyncio.run(coro)


def _json_messages(ws: FakeWebSocket) -> list[dict[str, object]]:
    return [json.loads(payload) for payload in ws.sent]


def test_connect_uses_token_header_and_cookie_ws_auth(monkeypatch):
    http_client = FakeHTTPClient(token="token-123")
    ws = FakeWebSocket()
    captured: dict[str, object] = {}

    monkeypatch.setattr(comet_client.httpx, "AsyncClient", lambda **_: http_client)

    async def fake_connect(url: str, **kwargs: object) -> FakeWebSocket:
        captured["url"] = url
        captured.update(kwargs)
        return ws

    monkeypatch.setattr(comet_client.websockets, "connect", fake_connect)

    async def run() -> tuple[CometClient, bool]:
        client = CometClient("comet.invalid", username="admin", password="secret", verify_ssl=False)
        connected = await client.connect()
        return client, connected

    client, connected = _run(run())
    try:
        assert connected is True
        assert http_client.headers.get("Token") == "token-123"
        assert any(c["url"].endswith("/api/auth/login") for c in http_client.post_calls)

        ws_url = str(captured["url"])
        parsed = urlparse(ws_url)
        assert parsed.scheme == "wss"
        assert parsed.path == "/api/ws"
        # Token must not appear in the logged/query URL.
        assert "auth_token" not in parse_qs(parsed.query)
        assert parse_qs(parsed.query) == {"stream": ["false"]}
        headers = captured.get("additional_headers") or captured.get("extra_headers") or {}
        assert headers.get("Token") == "token-123"
        assert "auth_token=token-123" in headers.get("Cookie", "")
        assert "secret" not in ws_url
    finally:
        _run(client.disconnect())

    assert any(c["url"].endswith("/api/auth/logout") for c in http_client.post_calls)
    assert http_client.closed is True
    assert ws.closed is True


def test_connect_closes_http_client_when_login_returns_no_auth_cookie(monkeypatch):
    http_client = FakeHTTPClient(token=None)
    monkeypatch.setattr(comet_client.httpx, "AsyncClient", lambda **_: http_client)

    async def run() -> None:
        client = CometClient("comet.invalid", password="secret")
        with pytest.raises(RuntimeError, match="no auth_token"):
            await client.connect()

    _run(run())
    assert http_client.closed is True


def test_send_combo_uses_modifier_wrapping_and_finish_on_keyup():
    ws = FakeWebSocket()
    client = CometClient("comet.invalid")
    client.ws = ws

    result = _run(client.send_combo("Ctrl+Alt+Delete"))

    assert result == {
        "sent": "Ctrl+Alt+Delete",
        "modifiers": ["ControlLeft", "AltLeft"],
        "key": "Delete",
    }
    messages = _json_messages(ws)
    assert messages == [
        {"event_type": "key", "event": {"key": "ControlLeft", "state": True, "finish": False}},
        {"event_type": "key", "event": {"key": "AltLeft", "state": True, "finish": False}},
        {"event_type": "key", "event": {"key": "Delete", "state": True, "finish": False}},
        {"event_type": "key", "event": {"key": "Delete", "state": False, "finish": True}},
        {"event_type": "key", "event": {"key": "AltLeft", "state": False, "finish": True}},
        {"event_type": "key", "event": {"key": "ControlLeft", "state": False, "finish": True}},
    ]


def test_watchdog_releases_unprotected_stale_keys():
    async def run() -> FakeWebSocket:
        ws = FakeWebSocket()
        client = CometClient("comet.invalid")
        client.ws = ws
        client.watchdog_period = 0.001
        client.stale_s = 0.001
        client.held["KeyA"] = HeldKey(pressed_at=0.0, watchdog_protected=False)
        task = asyncio.create_task(client._watchdog_loop())
        try:
            for _ in range(100):
                if not client.held and ws.sent:
                    break
                await asyncio.sleep(0.001)
            assert client.held == {}
            return ws
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    ws = _run(run())
    assert _json_messages(ws) == [
        {"event_type": "key", "event": {"key": "KeyA", "state": False, "finish": True}}
    ]


def test_watchdog_respects_intentional_hold():
    async def run() -> None:
        import time

        ws = FakeWebSocket()
        client = CometClient("comet.invalid")
        client.ws = ws
        client.watchdog_period = 0.001
        client.stale_s = 0.001
        client.held["Delete"] = HeldKey(
            pressed_at=time.monotonic(),
            release_deadline=time.monotonic() + 1.0,
            watchdog_protected=True,
        )
        task = asyncio.create_task(client._watchdog_loop())
        try:
            await asyncio.sleep(0.02)
            assert "Delete" in client.held
            assert ws.sent == []
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    _run(run())


def test_pinger_sends_ping_with_event_object_and_stops_on_websocket_failure():
    async def run() -> FakeWebSocket:
        ws = FakeWebSocket(fail_on_send=True)
        client = CometClient("comet.invalid")
        client.ws = ws
        client.ws_ping_period = 0.001
        await asyncio.wait_for(client._pinger_loop(), timeout=1)
        return ws

    ws = _run(run())
    assert _json_messages(ws) == [{"event_type": "ping", "event": {}}]


def test_receiver_tracks_pong_and_subsystem_state():
    async def run() -> CometClient:
        ws = FakeWebSocket()
        client = CometClient("comet.invalid")
        client.ws = ws
        client._ws_healthy = True
        task = asyncio.create_task(client._receiver_loop())
        try:
            await ws._recv_queue.put(json.dumps({"event_type": "pong", "event": {}}))
            await ws._recv_queue.put(json.dumps({
                "event_type": "atx_state",
                "event": {"enabled": True, "busy": False},
            }))
            for _ in range(50):
                if client.last_pong_at and "atx_state" in client.server_state:
                    break
                await asyncio.sleep(0.001)
            assert client.last_pong_at is not None
            assert client.server_state["atx_state"]["enabled"] is True
            return client
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    _run(run())


def test_atx_power_sends_query_params_and_maps_reset_alias():
    recorded: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        recorded["path"] = request.url.path
        recorded["params"] = dict(request.url.params)
        recorded["body"] = request.content
        return httpx.Response(200, json={"ok": True, "result": {}})

    async def run() -> None:
        client = CometClient("comet.invalid")
        client.http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            result = await client.atx_power("reset", wait=True)
            assert result["action"] == "reset_hard"
        finally:
            await client.http.aclose()

    _run(run())
    assert recorded["path"] == "/api/atx/power"
    assert recorded["params"]["action"] == "reset_hard"
    assert recorded["params"]["wait"] == "true"
    assert recorded["body"] in (b"", None) or recorded["body"] == b""


def test_atx_power_maps_board_unavailable_response_to_runtime_error():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/atx/power"
        assert "action" in request.url.params
        return httpx.Response(500, text="ATX board not connected")

    async def run() -> None:
        client = CometClient("comet.invalid")
        client.http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            with pytest.raises(RuntimeError, match="ATX board not detected"):
                await client.atx_power("reset")
        finally:
            await client.http.aclose()

    _run(run())


def test_atx_click_uses_query_params():
    recorded: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        recorded["path"] = request.url.path
        recorded["params"] = dict(request.url.params)
        return httpx.Response(200, json={"ok": True, "result": {}})

    async def run() -> None:
        client = CometClient("comet.invalid")
        client.http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            await client.atx_click("power_long", wait=False)
        finally:
            await client.http.aclose()

    _run(run())
    assert recorded["path"] == "/api/atx/click"
    assert recorded["params"] == {"button": "power_long", "wait": "false"}


def test_msd_upload_file_streams_raw_body_with_image_query(tmp_path: Path):
    recorded: dict[str, object] = {}
    media = tmp_path / "proxmox.iso"
    media.write_bytes(b"ISO-BYTES-123")

    async def handler(request: httpx.Request) -> httpx.Response:
        recorded["path"] = request.url.path
        recorded["params"] = dict(request.url.params)
        recorded["body"] = request.content
        recorded["content_length"] = request.headers.get("content-length")
        recorded["content_type"] = request.headers.get("content-type")
        return httpx.Response(200, json={"ok": True, "result": {}})

    async def run() -> dict:
        client = CometClient("comet.invalid")
        client.http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        client.auth_token = "tok"
        try:
            return await client.msd_upload_file(str(media), "proxmox.iso")
        finally:
            await client.http.aclose()

    result = _run(run())
    assert result["image"] == "proxmox.iso"
    assert result["bytes"] == len(b"ISO-BYTES-123")
    assert recorded["path"] == "/api/msd/write"
    assert recorded["params"]["image"] == "proxmox.iso"
    assert recorded["body"] == b"ISO-BYTES-123"
    assert recorded["content_length"] == str(len(b"ISO-BYTES-123"))
    assert "multipart" not in (recorded["content_type"] or "")


def test_msd_mount_sets_params_then_connects():
    calls: list[tuple[str, dict]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.url.path, dict(request.url.params)))
        return httpx.Response(200, json={"ok": True, "result": {}})

    async def run() -> None:
        client = CometClient("comet.invalid")
        client.http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            await client.msd_mount("proxmox.iso", mode="cdrom", read_only=True)
        finally:
            await client.http.aclose()

    _run(run())
    assert calls[0][0] == "/api/msd/set_params"
    assert calls[0][1] == {"image": "proxmox.iso", "cdrom": "true", "rw": "false"}
    assert calls[1][0] == "/api/msd/set_connected"
    assert calls[1][1] == {"connected": "true"}
