from __future__ import annotations

import io
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from src.kvm_core.ocr import OCRManager, ordered_lines, word_elements


RECORDED_TESSERACT_TSV = {
    "text": ["hello", "world", "READY", ""],
    "conf": ["90", "80", "96", "-1"],
    "left": [10, 60, 15, 0],
    "top": [10, 10, 50, 0],
    "width": [40, 50, 75, 0],
    "height": [10, 10, 12, 0],
    "page_num": [1, 1, 1, 1],
    "block_num": [1, 1, 1, 1],
    "par_num": [1, 1, 1, 1],
    "line_num": [1, 1, 2, 0],
}


def text_image(text: str = "COMET READY 42") -> bytes:
    image = Image.new("RGB", (800, 180), "white")
    draw = ImageDraw.Draw(image)
    candidates = [
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    font_path = next((path for path in candidates if path.is_file()), None)
    if font_path is None:
        pytest.skip("No stable TrueType test font installed")
    font = ImageFont.truetype(str(font_path), 64)
    draw.text((24, 45), text, fill="black", font=font)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_recorded_tsv_is_converted_to_ordered_lines_and_coordinates():
    assert ordered_lines(RECORDED_TESSERACT_TSV) == ["hello world", "READY"]

    elements = word_elements(RECORDED_TESSERACT_TSV, 200, 100)
    assert [element["text"] for element in elements] == ["hello", "world", "READY"]
    assert elements[0]["pixel"] == [30, 15]
    assert elements[0]["x_pct"] == 15.0


def test_recorded_tsv_search_filters_without_rewriting_coordinates():
    elements = word_elements(RECORDED_TESSERACT_TSV, 200, 100, "ready")
    assert elements == [{
        "text": "READY",
        "confidence": 96.0,
        "x_pct": 26.0,
        "y_pct": 56.0,
        "pixel": [52, 56],
        "box": [15, 50, 75, 12],
    }]


def test_real_tesseract_recognizes_generated_console_text():
    manager = OCRManager()
    if not manager.get_status()["available"]:
        pytest.skip("Tesseract binary is not installed")

    result = manager.run_ocr(text_image(), psm=7)

    assert "error" not in result
    assert "COMET" in result["text"].upper()
    assert "READY" in result["text"].upper()
    assert result["elements"]


def test_run_text_ocr_rejects_empty_crop():
    manager = OCRManager()

    with pytest.raises(ValueError, match="non-empty region"):
        manager.run_text_ocr(text_image(), crop=(20, 20, 10, 10))


def test_expect_tesseract_cmd_line(monkeypatch, tmp_path):
    import os
    import sys
    import subprocess
    from pathlib import Path

    mock_bin = tmp_path / "tesseract_mock.exe"
    mock_bin.touch()

    env = os.environ.copy()
    env["TESSERACT_PATH"] = str(mock_bin)

    res = subprocess.run(
        [sys.executable, "glkvm_mcp.py", "--expect-tesseract"],
        capture_output=True,
        text=True,
        env=env,
        cwd=Path(__file__).resolve().parents[1]
    )
    assert res.returncode == 0
    assert "Tesseract OCR is available" in res.stdout

    env["TESSERACT_PATH"] = "invalid_path_to_tesseract_non_existent"
    res2 = subprocess.run(
        [sys.executable, "glkvm_mcp.py", "--expect-tesseract"],
        capture_output=True,
        text=True,
        env=env,
        cwd=Path(__file__).resolve().parents[1]
    )
    assert res2.returncode == 1
    assert "ERROR: Tesseract OCR is not available" in res2.stderr or "ERROR: Tesseract OCR is not available" in res2.stdout
