"""RED specification for CometClient.get_screenshot 503 capture recovery.

Contract under specification (see docs/ MCP session lifecycle design):

* ``GET /api/streamer/snapshot`` returning **503** is the one and only retryable
  capture failure. The backoff schedule is exactly ``0.1, 0.2, 0.4, 0.8``
  seconds; after the fourth sleep is consumed the call raises a
  *capture-specific* error rather than leaking ``httpx.HTTPStatusError``.
* Every other status (401, 500, ...) raises immediately with zero sleeps.
* Between attempts the loop re-checks ``self.is_connected()`` and aborts the
  moment the session is gone (checked after the backoff sleep, before the next
  HTTP attempt).
* Session/auth state (``http``, ``auth_token``) survives an exhausted retry.

These tests drive a real loopback HTTP service and never sleep for real: the
client module's ``asyncio`` reference is swapped for a shim that records the
requested delays.
"""
from __future__ import annotations

import asyncio
from collections import deque
from typing import Any, Callable, Optional

import httpx
from aiohttp import web

import src.kvm_core.comet.client as client_mod
from src.kvm_core.comet.client import CometClient
from tests.bios_test_helpers import jpeg_bytes
from tests.local_services import CometProtocolService

SNAPSHOT_PATH = "/api/streamer/snapshot"
BACKOFF_SCHEDULE = [0.1, 0.2, 0.4, 0.8]


def run(coro):
    return asyncio.run(coro)


class QueuedCometService(CometProtocolService):
    """CometProtocolService whose staged responses can vary per request.

    ``respond(path, status, payload)`` (local_services.py) stages a single
    sticky response; capture retries need a *sequence*, so each queued entry is
    promoted into ``respond`` as it is consumed. The final entry stays sticky.
    """

    def __init__(self) -> None:
        super().__init__()
        self._queues: dict[str, deque[tuple[int, Any]]] = {}

    def enqueue(self, path: str, status: int, payload: Any) -> None:
        self._queues.setdefault(path, deque()).append((status, payload))

    def attempts(self, path: str) -> int:
        return sum(1 for row in self.requests if row["path"] == path)

    async def _handle(self, request: web.Request) -> web.StreamResponse:
        queue = self._queues.get(request.path)
        if queue:
            status, payload = queue.popleft() if len(queue) > 1 else queue[0]
            if isinstance(payload, (bytes, bytearray)):
                self.requests.append({
                    "method": request.method,
                    "path": request.path,
                    "query": dict(request.query),
                    "headers": dict(request.headers),
                    "body": b"",
                })
                return web.Response(
                    body=bytes(payload),
                    status=status,
                    content_type="image/jpeg",
                )
            self.respond(request.path, status, payload)
        return await super()._handle(request)


def install_sleep_recorder(
    monkeypatch,
    on_sleep: Optional[Callable[[float], None]] = None,
) -> list[float]:
    """Record every delay ``client.py`` asks ``asyncio.sleep`` for.

    Only the client module's ``asyncio`` binding is replaced, so the loopback
    aiohttp service keeps using the real event-loop primitives.
    """
    delays: list[float] = []
    real_asyncio = asyncio

    class RecordingAsyncio:
        def __getattr__(self, name: str) -> Any:
            return getattr(real_asyncio, name)

        async def sleep(self, delay: float, *args: Any, **kwargs: Any) -> None:
            delays.append(delay)
            if on_sleep is not None:
                on_sleep(delay)
            await real_asyncio.sleep(0)

    monkeypatch.setattr(client_mod, "asyncio", RecordingAsyncio())
    return delays


def make_shortcut_client(service: QueuedCometService, connected: bool = True) -> CometClient:
    """HTTP-only client (no full connect) with a truthful is_connected()."""
    client = CometClient(service.base_url)
    client.http = httpx.AsyncClient()
    client.auth_token = "token-123"
    client.is_connected = lambda: connected  # type: ignore[method-assign]
    return client


def test_snapshot_503_recovers_within_backoff_schedule(monkeypatch):
    delays = install_sleep_recorder(monkeypatch)
    image = jpeg_bytes()

    async def scenario() -> tuple[bytes, QueuedCometService]:
        async with QueuedCometService() as service:
            service.enqueue(SNAPSHOT_PATH, 503, {"error": "streamer not ready"})
            service.enqueue(SNAPSHOT_PATH, 503, {"error": "streamer not ready"})
            service.enqueue(SNAPSHOT_PATH, 200, image)
            client = make_shortcut_client(service)
            try:
                try:
                    data = await client.get_screenshot(preview=False)
                except Exception as exc:  # noqa: BLE001 - spec message matters
                    raise AssertionError(
                        "CometClient.get_screenshot must retry HTTP 503 from "
                        f"{SNAPSHOT_PATH} and recover; instead it raised "
                        f"{type(exc).__name__}: {exc}"
                    ) from exc
            finally:
                await client.http.aclose()
            return data, service

    data, service = run(scenario())
    assert data == image
    assert service.attempts(SNAPSHOT_PATH) == 3
    assert delays == BACKOFF_SCHEDULE[:2], (
        "503 capture recovery must consume only the delays it needs from the "
        f"0.1/0.2/0.4/0.8 backoff schedule; recorded {delays}"
    )


def test_snapshot_503_exhaustion_raises_capture_error_with_schedule(monkeypatch):
    delays = install_sleep_recorder(monkeypatch)

    async def scenario() -> tuple[BaseException | None, QueuedCometService, bool, Optional[str], bool]:
        async with QueuedCometService() as service:
            service.enqueue(SNAPSHOT_PATH, 503, {"error": "streamer not ready"})
            client = make_shortcut_client(service)
            error: BaseException | None = None
            try:
                await client.get_screenshot(preview=False)
            except BaseException as exc:  # noqa: BLE001 - inspect the raised type
                error = exc
            http_alive = client.http is not None
            token = client.auth_token
            still_connected = client.is_connected()
            if client.http is not None:
                await client.http.aclose()
            return error, service, http_alive, token, still_connected

    error, service, http_alive, token, still_connected = run(scenario())

    assert delays == BACKOFF_SCHEDULE, (
        "exhausted 503 capture retries must consume the full 0.1/0.2/0.4/0.8 "
        f"backoff schedule; recorded {delays}"
    )
    assert service.attempts(SNAPSHOT_PATH) == len(BACKOFF_SCHEDULE) + 1
    assert error is not None
    assert not isinstance(error, httpx.HTTPStatusError), (
        "exhausted 503 retries must raise a capture-specific error, not a raw "
        "httpx.HTTPStatusError"
    )
    signature = f"{type(error).__name__} {error}".lower()
    assert "capture" in signature, (
        "exhausted 503 retries must raise a capture-specific error naming the "
        f"capture failure; got {type(error).__name__}: {error}"
    )
    assert http_alive, "session/auth state must survive exhausted 503 retries"
    assert token == "token-123", "auth token must survive exhausted 503 retries"
    assert still_connected, "the session must remain connected after a capture failure"


def assert_status_never_retried(monkeypatch, status: int) -> None:
    delays = install_sleep_recorder(monkeypatch)

    async def scenario() -> tuple[BaseException | None, QueuedCometService]:
        async with QueuedCometService() as service:
            service.enqueue(SNAPSHOT_PATH, status, {"error": "nope"})
            client = make_shortcut_client(service)
            error: BaseException | None = None
            try:
                await client.get_screenshot(preview=False)
            except BaseException as exc:  # noqa: BLE001
                error = exc
            await client.http.aclose()
            return error, service

    error, service = run(scenario())
    assert error is not None, f"HTTP {status} from {SNAPSHOT_PATH} must raise"
    assert delays == [], (
        f"HTTP {status} from {SNAPSHOT_PATH} must never enter the 503 backoff "
        f"schedule; recorded sleeps {delays}"
    )
    assert service.attempts(SNAPSHOT_PATH) == 1, (
        f"HTTP {status} must be raised on the first attempt with no retry"
    )


def test_snapshot_401_never_retried(monkeypatch):
    assert_status_never_retried(monkeypatch, 401)


def test_snapshot_500_never_retried(monkeypatch):
    assert_status_never_retried(monkeypatch, 500)


def test_snapshot_retry_aborts_when_session_dies(monkeypatch):
    """A session that dies mid-loop aborts the retry instead of finishing it."""
    alive = {"value": True}

    def kill_session(_delay: float) -> None:
        alive["value"] = False

    delays = install_sleep_recorder(monkeypatch, on_sleep=kill_session)

    async def scenario() -> tuple[BaseException | None, QueuedCometService]:
        async with QueuedCometService() as service:
            service.enqueue(SNAPSHOT_PATH, 503, {"error": "streamer not ready"})
            client = CometClient(service.base_url)
            client.http = httpx.AsyncClient()
            client.auth_token = "token-123"
            client.is_connected = lambda: alive["value"]  # type: ignore[method-assign]
            error: BaseException | None = None
            try:
                await client.get_screenshot(preview=False)
            except BaseException as exc:  # noqa: BLE001
                error = exc
            await client.http.aclose()
            return error, service

    error, service = run(scenario())
    assert error is not None
    assert delays == BACKOFF_SCHEDULE[:1], (
        "the 503 retry loop must re-check is_connected() after each backoff "
        "sleep and abort as soon as the session dies; recorded sleeps "
        f"{delays}"
    )
    assert service.attempts(SNAPSHOT_PATH) == 1, (
        "no further snapshot request may be issued once the session is gone"
    )
