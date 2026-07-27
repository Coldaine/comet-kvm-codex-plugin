from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

from src.kvm_core.comet.client import CometClient
from src.kvm_core.comet.capture import CaptureManager
from src.kvm_core.doppler_credentials import resolve_comet_password
from src.kvm_core.ocr import OCRManager

LOG = logging.getLogger("kvm_core.runtime")

DEFAULT_TARGET = "default"
DEFAULT_COMET_HOST = "192.168.0.126"
DEFAULT_COMET_USERNAME = "admin"


def resolve_default_target() -> tuple[str, str]:
    """Return the managed default ``(host, username)``.

    Environment overrides win; otherwise the homelab Comet is hardcoded. Doppler
    holds the password only — it is never consulted for host or username.
    """
    host = (os.environ.get("COMET_HOST") or DEFAULT_COMET_HOST).strip()
    username = (os.environ.get("COMET_USERNAME") or DEFAULT_COMET_USERNAME).strip()
    return host, username


class TargetRuntime:
    """Per-Comet transport session."""

    def __init__(self, target_id: str, client: CometClient):
        self.target_id = target_id
        self.client = client


class KVMRuntime:
    """Owns physical-machine transport: Comet clients, frame capture, and OCR.

    Supports multiple concurrent Comet targets. ``client`` refers to the selected
    (default) target for backward-compatible tool calls.
    """

    def __init__(self, screenshot_cache: str = "state/screenshots"):
        self.capture_mgr = CaptureManager(cache_dir=screenshot_cache)
        self.ocr_mgr = OCRManager()
        self.targets: dict[str, TargetRuntime] = {}
        self.selected_target: str = DEFAULT_TARGET
        self.client: Optional[CometClient] = None
        # Lock ordering invariant: runtime locks are always acquired BEFORE any
        # client-internal lock (e.g. CometClient.send_lock). Never await a
        # runtime lock while holding a client lock. CometClient.connect()
        # internally takes send_lock, which is safe because that happens inside
        # our lock scope, not around it.
        self._connection_lock = asyncio.Lock()
        self._operation_lock = asyncio.Lock()

    def _sync_selected_client(self) -> None:
        selected = self.targets.get(self.selected_target)
        self.client = selected.client if selected else None

    async def connect(
        self,
        host: str,
        username: str = "admin",
        password: str = "",
        target: str | None = None,
        select: bool = True,
    ) -> bool:
        async with self._connection_lock:
            return await self._connect_locked(
                host=host,
                username=username,
                password=password,
                target=target,
                select=select,
            )

    async def _connect_locked(
        self,
        host: str,
        username: str = "admin",
        password: str = "",
        target: str | None = None,
        select: bool = True,
    ) -> bool:
        """Connect body. Caller MUST already hold ``_connection_lock``.

        ``asyncio.Lock`` is not re-entrant, so every public entry point takes the
        lock exactly once and then routes through here.
        """
        target_id = target or self.selected_target or DEFAULT_TARGET
        existing = self.targets.get(target_id)
        if existing:
            await existing.client.disconnect()
            del self.targets[target_id]

        client = CometClient(
            host=host,
            username=username,
            password=password,
            target_id=target_id,
        )
        await client.connect()
        was_empty = not self.targets
        self.targets[target_id] = TargetRuntime(target_id, client)
        # First connected target becomes selected even when select=False.
        if select or was_empty or self.selected_target == target_id:
            self.selected_target = target_id
        self._sync_selected_client()
        return True

    async def disconnect(self, target: str | None = None) -> None:
        async with self._connection_lock:
            await self._disconnect_locked(target)

    async def _disconnect_locked(self, target: str | None = None) -> None:
        """Disconnect body. Caller MUST already hold ``_connection_lock``."""
        if target is None:
            # Disconnect all when no target specified (legacy behavior for kvm_disconnect).
            for tid in list(self.targets.keys()):
                await self._disconnect_locked(tid)
            return
        entry = self.targets.pop(target, None)
        if entry:
            await entry.client.disconnect()
        if self.selected_target == target:
            self.selected_target = next(iter(self.targets), DEFAULT_TARGET)
        self._sync_selected_client()

    def _live_default_client(self) -> Optional[CometClient]:
        """The connected default-target client, if there is one."""
        entry = self.targets.get(DEFAULT_TARGET)
        client = entry.client if entry else None
        if client is None and self.selected_target == DEFAULT_TARGET:
            # Sidecar rigs may install a client directly on the runtime.
            client = self.client
        if client is not None and client.is_connected():
            return client
        return None

    async def ensure_connected(self, target: str | None = None) -> CometClient:
        """Return a live client for ``target``, connecting the default on demand.

        Only the ``default`` target is auto-managed. Named targets are the
        caller's to own: a named target that is not already connected fails
        closed rather than being silently dialled.
        """
        target_id = target or DEFAULT_TARGET

        if target_id != DEFAULT_TARGET:
            entry = self.targets.get(target_id)
            if entry is not None and entry.client.is_connected():
                return entry.client
            raise RuntimeError(
                f"Target '{target_id}' is not connected. Only the default target "
                f"is managed automatically; connect this one explicitly with "
                f"kvm_connect(host=..., target='{target_id}')."
            )

        live = self._live_default_client()
        if live is not None:
            return live

        async with self._connection_lock:
            # Double-check under the lock so concurrent cold ensures collapse
            # into a single connect (single-flight).
            live = self._live_default_client()
            if live is not None:
                return live
            host, username = resolve_default_target()
            password = resolve_comet_password()
            await self._connect_locked(
                host=host,
                username=username,
                password=password,
                target=DEFAULT_TARGET,
            )
            client = self.targets[DEFAULT_TARGET].client
            LOG.info("Managed default Comet session connected (%s@%s)", username, host)
            return client

    def select_target(self, target: str) -> str:
        if target not in self.targets:
            raise ValueError(f"Unknown target '{target}'. Connected: {sorted(self.targets)}")
        self.selected_target = target
        self._sync_selected_client()
        return target

    def get_client(self, target: str | None = None) -> CometClient:
        target_id = target or self.selected_target
        entry = self.targets.get(target_id)
        if entry is None or not entry.client.is_connected():
            raise RuntimeError(
                f"Not connected to target '{target_id}'. Call kvm_connect first."
            )
        return entry.client

    def is_connected(self, target: str | None = None) -> bool:
        if target is None:
            return self.client is not None and self.client.is_connected()
        entry = self.targets.get(target)
        return entry is not None and entry.client.is_connected()

    def list_targets(self) -> list[dict]:
        rows = []
        for tid, entry in self.targets.items():
            rows.append({
                "target": tid,
                "host": entry.client.base_url,
                "connected": entry.client.is_connected(),
                "selected": tid == self.selected_target,
                "capabilities": entry.client.capabilities,
            })
        return rows

    def set_screenshot_cache(self, screenshot_cache: str) -> None:
        """Use the requested cache for subsequent KVM and sidecar captures."""
        if self.capture_mgr.cache_dir != screenshot_cache:
            self.capture_mgr = CaptureManager(cache_dir=screenshot_cache)


_runtime: Optional[KVMRuntime] = None


def get_kvm_runtime(screenshot_cache: Optional[str] = None) -> KVMRuntime:
    global _runtime
    if _runtime is None:
        _runtime = KVMRuntime(screenshot_cache=screenshot_cache or "state/screenshots")
    elif screenshot_cache:
        _runtime.set_screenshot_cache(screenshot_cache)
    return _runtime
