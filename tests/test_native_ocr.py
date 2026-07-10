from __future__ import annotations

import asyncio
import io
from unittest.mock import patch

import httpx
import pytest
from PIL import Image

from src.kvm_core.comet.client import CometClient
from src.kvm_core.ocr import OCRManager
import src.kvm_core.tools as kvm_tools


def _jpeg_bytes() -> bytes:
    image = Image.new("RGB", (200, 100), "white")
    output = io.BytesIO()
    image.save(output, format="JPEG")
    return output.getvalue()


def test_comet_client_reads_native_ocr_state_and_text():
    calls = {"status": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/api/streamer/ocr"):
            calls["status"] += 1
            return httpx.Response(200, json={
                "ok": True,
                "result": {
                    "ocr": {
                        "enabled": True,
                        "engine": "rknn",
                        "langs": {"default": [], "available": []},
                    }
                },
            })
        assert request.url.params["ocr"] == "true"
        assert request.url.params["ocr_left"] == "10"
        assert request.url.params["ocr_langs"] == "eng"
        return httpx.Response(200, json={"ok": True, "result": "native text\n"})

    async def run():
        client = CometClient("example.invalid")
        client.http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            state = await client.get_ocr_state()
            cached = await client.get_ocr_state()
            text = await client.get_native_ocr_text("eng", (10, 20, 110, 80))
            return state, cached, text
        finally:
            await client.http.aclose()

    state, cached, text = asyncio.run(run())
    assert state["enabled"] is True
    assert cached == state
    assert calls["status"] == 1
    assert state["engine"] == "rknn"
    assert text == "native text\n"


def test_kvm_ocr_text_prefers_native_without_host_capture():
    class FakeClient:
        async def get_ocr_state(self):
            return {"enabled": True, "engine": "rknn", "langs": {"default": [], "available": []}}

        async def get_native_ocr_text(self, languages, crop):
            assert languages == "eng"
            assert crop == (10, 20, 110, 80)
            return "native output\n"

        async def get_screenshot(self, **kwargs):
            raise AssertionError("native OCR should avoid host screenshot capture")

    runtime = type("Runtime", (), {"ocr_mgr": OCRManager()})()
    with patch.object(kvm_tools, "_require_client", return_value=FakeClient()):
        with patch.object(kvm_tools, "get_kvm_runtime", return_value=runtime):
            result = asyncio.run(kvm_tools.kvm_ocr_text(
                languages="eng", left=10, top=20, right=110, bottom=80
            ))

    assert result["engine"] == "comet-native:rknn"
    assert result["text"] == "native output"
    assert result["lines"] == ["native output"]


def test_kvm_ocr_text_validates_psm_before_native_call():
    class FakeClient:
        async def get_ocr_state(self):
            raise AssertionError("invalid input should fail before capability I/O")

    runtime = type("Runtime", (), {"ocr_mgr": OCRManager()})()
    with patch.object(kvm_tools, "_require_client", return_value=FakeClient()):
        with patch.object(kvm_tools, "get_kvm_runtime", return_value=runtime):
            with pytest.raises(ValueError, match="psm"):
                asyncio.run(kvm_tools.kvm_ocr_text(psm=2))


def test_kvm_ocr_text_falls_back_when_native_is_disabled(monkeypatch):
    class FakeClient:
        async def get_ocr_state(self):
            return {"enabled": False, "engine": "tesseract", "langs": {"default": [], "available": []}}

        async def get_screenshot(self, **kwargs):
            return _jpeg_bytes()

    manager = OCRManager()
    manager.tesseract_bin = "tesseract"
    monkeypatch.setattr(
        manager,
        "run_text_ocr",
        lambda *args: {
            "width": 200,
            "height": 100,
            "text": "host output",
            "lines": ["host output"],
            "tesseract_found": True,
        },
    )
    runtime = type("Runtime", (), {"ocr_mgr": manager})()

    with patch.object(kvm_tools, "_require_client", return_value=FakeClient()):
        with patch.object(kvm_tools, "get_kvm_runtime", return_value=runtime):
            result = asyncio.run(kvm_tools.kvm_ocr_text())

    assert result["engine"] == "host-tesseract"
    assert result["fallback_reason"] == "device OCR is disabled"
    assert result["text"] == "host output"


def test_kvm_ocr_click_propagates_ocr_failure(monkeypatch):
    class FakeClient:
        async def get_screenshot(self, **kwargs):
            return _jpeg_bytes()

    manager = OCRManager()
    monkeypatch.setattr(manager, "run_ocr", lambda *args: {"elements": [], "error": "OCR timed out"})
    runtime = type("Runtime", (), {"ocr_mgr": manager})()

    with patch.object(kvm_tools, "_require_client", return_value=FakeClient()):
        with patch.object(kvm_tools, "get_kvm_runtime", return_value=runtime):
            with pytest.raises(RuntimeError, match="OCR timed out"):
                asyncio.run(kvm_tools.kvm_ocr_click("Save"))


def test_kvm_ocr_status_reports_unavailable_without_any_engine(monkeypatch):
    class FakeClient:
        async def get_ocr_state(self, refresh=False):
            return {"enabled": False, "engine": "tesseract", "langs": {"default": [], "available": []}}

    manager = OCRManager()
    monkeypatch.setattr(manager, "get_status", lambda: {"available": False, "command": "", "timeout_seconds": 15})
    runtime = type("Runtime", (), {"ocr_mgr": manager})()

    with patch.object(kvm_tools, "_require_client", return_value=FakeClient()):
        with patch.object(kvm_tools, "get_kvm_runtime", return_value=runtime):
            result = asyncio.run(kvm_tools.kvm_ocr_status())

    assert result["recommended_text_engine"] == "unavailable"
