from __future__ import annotations

import asyncio

import pytest

import src.kvm_core.tools as kvm_tools
from src.kvm_core.runtime import KVMRuntime, TargetRuntime
from tests.bios_test_helpers import ScriptedCometClient, installed_kvm_runtime
from tests.test_ocr import text_image


def configured_runtime(tmp_path, screenshot: bytes) -> tuple[KVMRuntime, ScriptedCometClient]:
    runtime = KVMRuntime(screenshot_cache=str(tmp_path / "shots"))
    client = ScriptedCometClient(screenshot=screenshot)
    runtime.targets["default"] = TargetRuntime("default", client)
    runtime._sync_selected_client()
    return runtime, client


def test_ocr_status_reports_browser_engine_as_product_ui_only(tmp_path):
    runtime, _ = configured_runtime(tmp_path, text_image())
    with installed_kvm_runtime(runtime):
        result = asyncio.run(kvm_tools.kvm_ocr_status())

    assert result["product_ui_ocr"] == {
        "engine": "tesseract.js",
        "execution": "controlling-browser",
        "available_to_mcp": False,
    }
    assert result["recommended_text_engine"] in {"host-tesseract", "unavailable"}


def test_ocr_text_validates_psm_before_capture(tmp_path):
    runtime, client = configured_runtime(tmp_path, text_image())
    with installed_kvm_runtime(runtime):
        with pytest.raises(ValueError, match="psm"):
            asyncio.run(kvm_tools.kvm_ocr_text(psm=2))

    assert client.screenshot_calls == 0


def test_ocr_text_uses_real_host_tesseract_when_installed(tmp_path):
    runtime, _ = configured_runtime(tmp_path, text_image())
    if not runtime.ocr_mgr.get_status()["available"]:
        pytest.skip("Tesseract binary is not installed")

    with installed_kvm_runtime(runtime):
        result = asyncio.run(kvm_tools.kvm_ocr_text(psm=7))

    assert result["engine"] == "host-tesseract"
    assert "COMET" in result["text"].upper()
    assert result["crop"] is None


def test_ocr_click_surfaces_real_decode_failure(tmp_path):
    runtime, _ = configured_runtime(tmp_path, b"not-an-image")
    with installed_kvm_runtime(runtime):
        with pytest.raises(RuntimeError, match="OCR error"):
            asyncio.run(kvm_tools.kvm_ocr_click("Save"))
