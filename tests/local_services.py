"""Executable loopback services used by contract and sidecar tests."""
from __future__ import annotations

import json
import threading
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from aiohttp import web


DEFAULT_BIOS_PARSE = {
    "screen_title": "Advanced SETTINGS",
    "menu_path": ["SETTINGS"],
    "cursor_at": 0,
    "entries": [
        {
            "label": "Advanced",
            "type": "submenu",
            "value": None,
            "options": None,
            "key_to_enter": "Enter",
        }
    ],
    "blocklist_flag": False,
    "blocklist_keywords": [],
}


class OpenAICompatibleService:
    """Small real HTTP service implementing the endpoint used by ``VLMClient``."""

    def __init__(self, responses: list[tuple[int, dict[str, Any]]] | None = None) -> None:
        self.requests: list[dict[str, Any]] = []
        self._responses = deque(responses or [])
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length))
                owner.requests.append(body)
                status, payload = owner._next_response()
                encoded = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def log_message(self, format: str, *args: object) -> None:
                return

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    @property
    def base_url(self) -> str:
        host, port = self._server.server_address
        return f"http://{host}:{port}/v1"

    def enqueue_parse(self, parse: dict[str, Any], status: int = 200) -> None:
        self._responses.append((status, self._completion(parse)))

    def enqueue_payload(self, status: int, payload: dict[str, Any]) -> None:
        self._responses.append((status, payload))

    @staticmethod
    def _completion(parse: dict[str, Any]) -> dict[str, Any]:
        return {"choices": [{"message": {"content": json.dumps(parse)}}]}

    def _next_response(self) -> tuple[int, dict[str, Any]]:
        if self._responses:
            return self._responses.popleft()
        return 200, self._completion(DEFAULT_BIOS_PARSE)

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)

    def __enter__(self) -> "OpenAICompatibleService":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()


class CometProtocolService:
    """Loopback HTTP/WebSocket service implementing observed Comet contracts."""

    def __init__(self, *, issue_auth_cookie: bool = True) -> None:
        self.issue_auth_cookie = issue_auth_cookie
        self.requests: list[dict[str, Any]] = []
        self.ws_messages: list[dict[str, Any]] = []
        self.ws_headers: dict[str, str] = {}
        self.ws_query: dict[str, str] = {}
        self.responses: dict[str, tuple[int, Any]] = {}
        self._runner: web.AppRunner | None = None
        self.base_url = ""

    async def __aenter__(self) -> "CometProtocolService":
        app = web.Application()
        app.router.add_route("*", "/{tail:.*}", self._handle)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "127.0.0.1", 0)
        await site.start()
        socket = site._server.sockets[0]
        host, port = socket.getsockname()[:2]
        self.base_url = f"http://{host}:{port}"
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self._runner is not None:
            await self._runner.cleanup()

    def respond(self, path: str, status: int, payload: Any) -> None:
        self.responses[path] = (status, payload)

    async def _handle(self, request: web.Request) -> web.StreamResponse:
        if request.path == "/api/ws":
            return await self._websocket(request)

        body = await request.read()
        self.requests.append({
            "method": request.method,
            "path": request.path,
            "query": dict(request.query),
            "headers": dict(request.headers),
            "body": body,
        })
        if request.path == "/api/auth/login":
            response = web.json_response({"ok": True, "result": {}})
            if self.issue_auth_cookie:
                response.set_cookie("auth_token", "token-123")
            return response

        status, payload = self.responses.get(
            request.path,
            (200, {"ok": True, "result": {}}),
        )
        if isinstance(payload, (dict, list)):
            return web.json_response(payload, status=status)
        return web.Response(text=str(payload), status=status)

    async def _websocket(self, request: web.Request) -> web.WebSocketResponse:
        self.ws_headers = dict(request.headers)
        self.ws_query = dict(request.query)
        ws = web.WebSocketResponse(autoping=False)
        await ws.prepare(request)
        await ws.send_json({
            "event_type": "atx_state",
            "event": {"enabled": True, "busy": False},
        })
        async for message in ws:
            if message.type != web.WSMsgType.TEXT:
                continue
            payload = json.loads(message.data)
            self.ws_messages.append(payload)
            if payload.get("event_type") == "ping":
                await ws.send_json({"event_type": "pong", "event": {}})
        return ws
