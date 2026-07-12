"""Shared helpers for offline BIOS sidecar tests (no live hardware)."""
from __future__ import annotations

import io
from typing import Any, Optional
from unittest.mock import AsyncMock

from PIL import Image as PILImage

import src.kvm_core.runtime as kvm_runtime_mod
from src.bios_sidecar.controller.runtime import StatefulBiosRuntime
from src.bios_sidecar.domain.enums import ControlRole, RiskClass, RuntimeState, StateKind
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


def jpeg_bytes(color: tuple[int, int, int] = (40, 80, 120), size: tuple[int, int] = (64, 48)) -> bytes:
    img = PILImage.new("RGB", size, color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def fake_ocr_result(
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


class FakeCometClient:
    """CometClient stand-in that records HID traffic and returns canned frames."""

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
            StateKind.MENU_LIST,
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
    """Fresh StatefulBiosRuntime with FakeCometClient and fast settle/OCR stubs."""
    kvm_runtime_mod._runtime = None
    shots = tmp_path / "shots"
    shots.mkdir()
    db = tmp_path / "bios.db"
    runtime = StatefulBiosRuntime(
        db_path=str(db),
        screenshot_cache=str(shots),
        vlm_provider="mock",
    )
    client = FakeCometClient(host=host, screenshot=screenshot or jpeg_bytes())
    runtime.kvm.client = client

    ocr_payload = fake_ocr_result()

    def _ocr(_img: bytes, search_text: str = "", psm: int = 3) -> dict:
        return dict(ocr_payload)

    runtime.ocr_mgr.run_ocr = _ocr  # type: ignore[method-assign]

    async def _instant_settle(c):
        return await c.get_screenshot(preview=False)

    runtime.settler.wait_for_settle = AsyncMock(side_effect=_instant_settle)
    runtime.settler.wait_fixed = AsyncMock()
    return runtime, client


def cleanup_runtime(runtime: StatefulBiosRuntime) -> None:
    try:
        runtime.store.close()
    finally:
        kvm_runtime_mod._runtime = None


def patch_ocr_texts(runtime: StatefulBiosRuntime, texts: list[str]) -> None:
    payload = fake_ocr_result(texts)

    def _ocr(_img: bytes, search_text: str = "", psm: int = 3) -> dict:
        return dict(payload)

    runtime.ocr_mgr.run_ocr = _ocr  # type: ignore[method-assign]
