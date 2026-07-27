from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP

LOG = logging.getLogger("kvm_core.server")

INSTRUCTIONS = """This server manages its own connection to the default Comet KVM appliance
(host from COMET_HOST, default 192.168.0.126; password via Doppler CLI).
Call the operation you want — screenshot, OCR, HID, power, media, BIOS —
and the server will establish or reuse a healthy session automatically.

- kvm_connect is OPTIONAL: use it only for a non-default host, explicit
  credentials, a named multi-target session, or force_reconnect=True.
- kvm_status observes without connecting; it never warms anything up.
- kvm_disconnect closes the session now (freeing the device streamer);
  it is not required cleanup, and the next device operation reconnects.
- A snapshot HTTP 503 is a capture-path condition (streamer warming up),
  NOT an authentication failure — the session remains healthy and the
  server retries briefly on its own. Do not reconnect to "fix" it.
- ATX power state with enabled=false means no ATX header is attached —
  classify machine state from the console image, not that field.
- Automatic connection covers transport only: requested actions are
  executed exactly once and never replayed after a failure."""


async def _shutdown_cleanup() -> None:
    """Best-effort release of held keys and Comet sessions. Never raises.

    The runtime module is imported lazily (server.py is imported by every tool
    module) and the process-global runtime is read directly rather than through
    ``get_kvm_runtime()`` so shutdown never *creates* a runtime.
    """
    try:
        from src.kvm_core import runtime as runtime_mod

        runtime = runtime_mod._runtime
        if runtime is None:
            return
        clients = [
            getattr(entry, "client", None)
            for entry in list(getattr(runtime, "targets", {}).values())
        ]
        direct_client = getattr(runtime, "client", None)
        if direct_client is not None and all(client is not direct_client for client in clients):
            clients.append(direct_client)
        for client in clients:
            if client is None:
                continue
            try:
                if client.is_connected():
                    await client.release_all()
            except Exception:  # noqa: BLE001 - shutdown is best effort
                LOG.debug("release_all during shutdown failed", exc_info=True)
        try:
            await runtime.disconnect()
        except Exception:  # noqa: BLE001 - shutdown is best effort
            LOG.debug("disconnect during shutdown failed", exc_info=True)
    except Exception:  # noqa: BLE001 - shutdown is best effort
        LOG.debug("managed session cleanup failed", exc_info=True)


@asynccontextmanager
async def managed_session_lifespan(server: FastMCP) -> AsyncIterator[None]:
    """Never connects at startup; cleans up any live session at shutdown."""
    try:
        yield
    finally:
        await _shutdown_cleanup()


mcp = FastMCP(
    "comet-kvm",
    instructions=INSTRUCTIONS,
    lifespan=managed_session_lifespan,
)
