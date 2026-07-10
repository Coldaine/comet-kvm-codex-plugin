import io

import pytesseract
import pytest
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
    assert seen["timeout"] == 15
    assert (result["width"], result["height"]) == (200, 100)


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


def test_run_text_ocr_preserves_spacing_and_crop(monkeypatch):
    manager = OCRManager()
    manager.tesseract_bin = "tesseract"
    seen = {}

    def fake_image_to_string(image, **kwargs):
        seen.update(kwargs)
        seen["size"] = image.size
        return "name      value\nrow       42\n"

    monkeypatch.setattr(pytesseract, "image_to_string", fake_image_to_string)

    result = manager.run_text_ocr(
        _jpeg_bytes(),
        psm=6,
        languages="eng, deu",
        crop=(10, 5, 110, 55),
    )

    assert result["text"] == "name      value\nrow       42"
    assert result["lines"] == ["name      value", "row       42"]
    assert seen["config"] == "--psm 6 -c preserve_interword_spaces=1"
    assert seen["lang"] == "eng+deu"
    assert seen["timeout"] == 15
    assert seen["size"] == (100, 50)


def test_run_text_ocr_rejects_empty_crop():
    manager = OCRManager()
    manager.tesseract_bin = "tesseract"

    with pytest.raises(ValueError, match="non-empty region"):
        manager.run_text_ocr(_jpeg_bytes(), crop=(20, 20, 10, 10))
