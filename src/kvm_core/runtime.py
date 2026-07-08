from __future__ import annotations

import logging
from typing import Optional

from src.kvm_core.comet.client import CometClient
from src.kvm_core.comet.capture import CaptureManager
from src.kvm_core.ocr import OCRManager

LOG = logging.getLogger("kvm_core.runtime")


class KVMRuntime:
    """Owns the physical-machine transport: Comet client, frame capture, and OCR.

    The BIOS sidecar runtime delegates connection lifecycle and media capture to
    this core so the transport layer is shared and never duplicated.
    """

    def __init__(self, screenshot_cache: str = "state/screenshots"):
        self.capture_mgr = CaptureManager(cache_dir=screenshot_cache)
        self.ocr_mgr = OCRManager()
        self.client: Optional[CometClient] = None

    async def connect(self, host: str, username: str = "admin", password: str = "") -> bool:
        if self.client:
            await self.disconnect()
        self.client = CometClient(host=host, username=username, password=password)
        await self.client.connect()
        return True

    async def disconnect(self):
        if self.client:
            await self.client.disconnect()
            self.client = None

    def is_connected(self) -> bool:
        return self.client is not None and self.client.is_connected()


_runtime: Optional[KVMRuntime] = None


def get_kvm_runtime() -> KVMRuntime:
    global _runtime
    if _runtime is None:
        _runtime = KVMRuntime()
    return _runtime
