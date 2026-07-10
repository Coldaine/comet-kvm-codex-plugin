import io

import pytesseract
from PIL import Image

from src.kvm_core.ocr import OCRManager


def _jpeg_bytes() -> bytes:
    image = Image.new("RGB", (200, 100), "white")
    output = io.BytesIO()
    image.save(output, format="JPEG")
    return output.getvalue()


def test_run_ocr_returns_ordered_text_and_coordinates(monkeypatch):
    manager = OCRManager()
    manager.tesseract_bin = "tesseract"
    data = {
        "text": ["hello", "world"],
        "conf": ["90", "80"],
        "left": [10, 60],
        "top": [10, 10],
        "width": [40, 50],
        "height": [10, 10],
        "page_num": [1, 1],
        "block_num": [1, 1],
        "par_num": [1, 1],
        "line_num": [1, 1],
    }
    seen = {}

    def fake_image_to_data(*args, **kwargs):
        seen.update(kwargs)
        return data

    monkeypatch.setattr(pytesseract, "image_to_data", fake_image_to_data)

    result = manager.run_ocr(_jpeg_bytes(), psm=6)

    assert result["text"] == "hello world"
    assert result["lines"] == ["hello world"]
    assert [element["text"] for element in result["elements"]] == ["hello", "world"]
    assert seen["config"] == "--psm 6"


def test_run_ocr_rediscovers_tesseract_without_restart(monkeypatch):
    manager = OCRManager()
    manager.tesseract_bin = None
    monkeypatch.setattr(manager, "_find_tesseract_binary", lambda: "new-tesseract")
    monkeypatch.setattr(
        pytesseract,
        "image_to_data",
        lambda *args, **kwargs: {
            "text": ["ready"],
            "conf": ["90"],
            "left": [10],
            "top": [10],
            "width": [40],
            "height": [10],
            "page_num": [1],
            "block_num": [1],
            "par_num": [1],
            "line_num": [1],
        },
    )

    result = manager.run_ocr(_jpeg_bytes())

    assert result["tesseract_found"] is True
    assert result["text"] == "ready"
