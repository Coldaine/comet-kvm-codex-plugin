from __future__ import annotations

import logging
from typing import Optional

from src.kvm_core.comet.client import CometClient
from src.kvm_core.comet.capture import CaptureManager
from src.kvm_core.ocr import OCRManager

LOG = logging.getLogger("kvm_core.runtime")


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
        self.selected_target: str = "default"
        self.client: Optional[CometClient] = None

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
        target_id = target or self.selected_target or "default"
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
        if target is None:
            # Disconnect all when no target specified (legacy behavior for kvm_disconnect).
            for tid in list(self.targets.keys()):
                await self.disconnect(tid)
            return
        entry = self.targets.pop(target, None)
        if entry:
            await entry.client.disconnect()
        if self.selected_target == target:
            self.selected_target = next(iter(self.targets), "default")
        self._sync_selected_client()

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
