"""Shared helpers for offline BIOS sidecar tests (no live hardware)."""
from __future__ import annotations

import io
import asyncio
from contextlib import contextmanager
from collections import deque
from typing import Any, Optional

from PIL import Image as PILImage

import src.kvm_core.runtime as kvm_runtime_mod
from src.bios_sidecar.controller.runtime import StatefulBiosRuntime
from src.bios_sidecar.perception.vlm_client import VLMClient
from src.bios_sidecar.domain.enums import ControlRole, RiskClass, StateKind
from src.bios_sidecar.domain.models import (
    ActionPolicies,
    BiosMetadata,
    BiosState,
    ConfidenceMetrics,
    ControlEntry,
    FrameMetadata,
    LocationMetadata,
    ModalMetadata,
    RiskStatus,
    SelectionMetadata,
)
from src.kvm_core.runtime import KVMRuntime
from tests.local_services import OpenAICompatibleService


def jpeg_bytes(color: tuple[int, int, int] = (40, 80, 120), size: tuple[int, int] = (64, 48)) -> bytes:
    img = PILImage.new("RGB", size, color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def recorded_ocr_result(
    texts: Optional[list[str]] = None,
    width: int = 64,
    height: int = 48,
) -> dict[str, Any]:
    words = texts or ["SETTINGS", "Advanced"]
    return {
        "width": width,
        "height": height,
        "text": " ".join(words),
        "lines": [],
        "elements": [{"text": w, "confidence": 95.0} for w in words],
        "tesseract_found": True,
    }


class ScriptedCometClient:
    """Deterministic virtual Comet that records HID traffic and serves frames."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        screenshot: Optional[bytes] = None,
        connected: bool = True,
    ):
        self.host = host
        self.base_url = f"https://{host}"
        self._connected = connected
        self.screenshot = screenshot or jpeg_bytes()
        self.sent_combos: list[str] = []
        self.release_calls = 0
        self.screenshot_calls = 0

    def is_connected(self) -> bool:
        return self._connected

    async def get_screenshot(
        self, preview: bool = True, max_width: int = 1024, quality: int = 60
    ) -> bytes:
        self.screenshot_calls += 1
        return self.screenshot

    async def send_combo(self, combo: str) -> dict:
        self.sent_combos.append(combo)
        return {"sent": combo, "modifiers": [], "key": combo}

    async def release_all(self) -> dict:
        self.release_calls += 1
        return {"released": []}


def make_bios_state(
    *,
    state_id: str = "state_test",
    screen_title: str = "Advanced SETTINGS",
    screen_kind: StateKind = StateKind.MENU_LIST,
    controls: Optional[list[ControlEntry]] = None,
    modal_present: bool = False,
    modal_type: Optional[str] = None,
    phash: str = "aabbccddeeff0011",
    selected_label: Optional[str] = None,
    selected_value: Optional[str] = None,
) -> BiosState:
    if controls is None:
        controls = [
            ControlEntry(
                "ctrl_000",
                "Advanced",
                None,
                ControlRole.SUBMENU,
                True,
                RiskClass.LOW,
            )
        ]
    selected = next((c for c in controls if c.selected), None)
    return BiosState(
        state_id=state_id,
        run_id="run_test",
        device_id="device_test",
        frame=FrameMetadata("shot_1", "sha", phash, [64, 48], "2026-07-12T00:00:00"),
        bios=BiosMetadata("msi", "z690", "click_bios", "advanced"),
        location=LocationMetadata(
            screen_kind,
            "SETTINGS",
            ["SETTINGS"],
            screen_title=screen_title,
        ),
        selection=SelectionMetadata(
            0,
            selected_label or (selected.label if selected else None),
            selected_value or (selected.value if selected else None),
        ),
        controls=controls,
        modal=ModalMetadata(present=modal_present, type=modal_type),
        risk=RiskStatus(blocklist_flag=False),
        actions=ActionPolicies(safe=["ArrowDown", "Escape"], context_gated=["Enter"]),
        confidence=ConfidenceMetrics(0.9, 0.9, 0.9),
    )


def build_runtime(tmp_path, *, host: str = "127.0.0.1", screenshot: Optional[bytes] = None):
    """Fresh sidecar driven by loopback VLM and deterministic virtual hardware."""
    kvm_runtime_mod._runtime = None
    shots = tmp_path / "shots"
    shots.mkdir()
    db = tmp_path / "bios.db"
    vlm_service = OpenAICompatibleService()
    vlm_client = VLMClient(
        provider="vllm",
        model="recorded-bios",
        base_url=vlm_service.base_url,
    )
    kvm_runtime = KVMRuntime(screenshot_cache=str(shots))
    runtime = StatefulBiosRuntime(
        db_path=str(db),
        screenshot_cache=str(shots),
        kvm_runtime=kvm_runtime,
        vlm_client=vlm_client,
    )
    client = ScriptedCometClient(host=host, screenshot=screenshot or jpeg_bytes())
    runtime.kvm.client = client
    runtime._test_vlm_service = vlm_service

    ocr_payload = recorded_ocr_result()

    def _ocr(_img: bytes, search_text: str = "", psm: int = 3) -> dict:
        return dict(ocr_payload)

    runtime.ocr_mgr.run_ocr = _ocr  # type: ignore[method-assign]

    class InstantSettler:
        async def wait_for_settle(self, c):
            return await c.get_screenshot(preview=False)

        async def wait_fixed(self, *args, **kwargs):
            return None

    runtime.settler = InstantSettler()
    runtime.crawler.settler = runtime.settler
    runtime.navigator.settler = runtime.settler
    runtime.mutator.settler = runtime.settler
    runtime.recovery.settler = runtime.settler
    return runtime, client


def cleanup_runtime(runtime: StatefulBiosRuntime) -> None:
    try:
        asyncio.run(runtime.vlm_client.close())
        service = getattr(runtime, "_test_vlm_service", None)
        if service is not None:
            service.close()
        runtime.store.close()
    finally:
        kvm_runtime_mod._runtime = None


def install_recorded_ocr(runtime: StatefulBiosRuntime, texts: list[str]) -> None:
    payload = recorded_ocr_result(texts)

    def _ocr(_img: bytes, search_text: str = "", psm: int = 3) -> dict:
        return dict(payload)

    runtime.ocr_mgr.run_ocr = _ocr  # type: ignore[method-assign]


class ScriptedObserver:
    """Finite sequence of observed BIOS states with a useful call count."""

    def __init__(self, states: list[BiosState], store: Any = None) -> None:
        self._states = deque(states)
        self.calls = 0
        self.store = store

    async def observe_state(self, *args, **kwargs) -> BiosState:
        self.calls += 1
        if len(self._states) > 1:
            return self._states.popleft()
        return self._states[0]


class NoWaitSettler:
    """Settler for deterministic rigs that records every requested boundary."""

    def __init__(self) -> None:
        self.fixed_waits: list[float] = []
        self.settle_calls = 0

    async def wait_fixed(self, seconds: float) -> None:
        self.fixed_waits.append(seconds)

    async def wait_for_settle(self, client) -> bytes:
        self.settle_calls += 1
        return await client.get_screenshot(preview=False)


@contextmanager
def installed_bios_runtime(runtime: StatefulBiosRuntime):
    """Install a concrete runtime in the MCP facade for one test transaction."""
    from src.bios_sidecar.mcp import server as bios_server

    previous = bios_server._runtime
    bios_server._runtime = runtime
    try:
        yield runtime
    finally:
        bios_server._runtime = previous


@contextmanager
def installed_kvm_runtime(runtime: KVMRuntime):
    """Install a concrete KVM runtime for one tool-level test transaction."""
    previous = kvm_runtime_mod._runtime
    kvm_runtime_mod._runtime = runtime
    try:
        yield runtime
    finally:
        kvm_runtime_mod._runtime = previous
