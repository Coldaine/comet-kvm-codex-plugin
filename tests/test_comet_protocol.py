from __future__ import annotations

import asyncio
import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from src.kvm_core.comet import client as comet_client
from src.kvm_core.comet.client import CometClient


class FakeResponse:
    def __init__(self, status_code: int = 200, text: str = "ok") -> None:
        self.status_code = status_code
        self.text = text
        self.is_success = status_code < 400

    def raise_for_status(self) -> None:
        if not self.is_success:
            raise httpx.HTTPStatusError(
                "request failed",
                request=httpx.Request("POST", "https://comet.invalid"),
                response=httpx.Response(self.status_code, text=self.text),
            )


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
        self.post_calls: list[dict[str, object]] = []
        self.closed = False

    async def post(self, url: str, **kwargs: object) -> FakeResponse:
        self.post_calls.append({"url": url, **kwargs})
        return FakeResponse()

    async def aclose(self) -> None:
        self.closed = True


class FakeWebSocket:
    def __init__(self, fail_on_send: bool = False) -> None:
        self.sent: list[str] = []
        self.closed = False
        self.fail_on_send = fail_on_send

    async def send(self, payload: str) -> None:
        self.sent.append(payload)
        if self.fail_on_send:
            raise RuntimeError("send failed")

    async def close(self) -> None:
        self.closed = True


def _run(coro):
    return asyncio.run(coro)


def _json_messages(ws: FakeWebSocket) -> list[dict[str, object]]:
    return [json.loads(payload) for payload in ws.sent]


def test_connect_posts_credentials_and_uses_auth_cookie_for_websocket(monkeypatch):
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
        assert http_client.post_calls == [
            {
                "url": "https://comet.invalid/api/auth/login",
                "data": {"user": "admin", "passwd": "secret", "expire": "0"},
            }
        ]

        ws_url = str(captured["url"])
        parsed = urlparse(ws_url)
        assert parsed.scheme == "wss"
        assert parsed.netloc == "comet.invalid"
        assert parsed.path == "/api/ws"
        assert parse_qs(parsed.query) == {"auth_token": ["token-123"], "stream": ["false"]}
        assert "secret" not in ws_url
        assert captured["ping_interval"] is None
        assert captured["max_size"] == 8 * 1024 * 1024
    finally:
        _run(client.disconnect())

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


def test_watchdog_releases_stale_keys():
    async def run() -> FakeWebSocket:
        ws = FakeWebSocket()
        client = CometClient("comet.invalid")
        client.ws = ws
        client.watchdog_period = 0.001
        client.stale_s = 0.001
        client.held["KeyA"] = 0.0
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
            await task

    ws = _run(run())
    assert _json_messages(ws) == [
        {"event_type": "key", "event": {"key": "KeyA", "state": False, "finish": True}}
    ]


def test_pinger_sends_ping_and_stops_on_websocket_failure():
    async def run() -> FakeWebSocket:
        ws = FakeWebSocket(fail_on_send=True)
        client = CometClient("comet.invalid")
        client.ws = ws
        client.ws_ping_period = 0.001
        await asyncio.wait_for(client._pinger_loop(), timeout=1)
        return ws

    ws = _run(run())
    assert _json_messages(ws) == [{"event_type": "ping"}]


def test_atx_power_maps_board_unavailable_response_to_runtime_error():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/atx/power"
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
