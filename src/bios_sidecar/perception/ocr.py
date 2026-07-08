from __future__ import annotations
import io
import os
import shutil
import struct
import pytesseract
from PIL import Image as PILImage

class OCRManager:
    def __init__(self):
        self.tesseract_bin = self._find_tesseract_binary()
        if self.tesseract_bin:
            pytesseract.pytesseract.tesseract_cmd = self.tesseract_bin

    def _find_tesseract_binary(self) -> str | None:
        env_path = os.environ.get("TESSERACT_PATH") or os.environ.get("TESSERACT_CMD")
        if env_path and os.path.isfile(env_path):
            return env_path
        found = shutil.which("tesseract")
        if found:
            return found
        if os.name == "nt":
            for candidate in (
                r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            ):
                if os.path.isfile(candidate):
                    return candidate
        return None

    def get_jpeg_dimensions(self, data: bytes) -> tuple[int, int]:
        i = 0
        while i < len(data) - 1:
            if data[i] == 0xFF and data[i + 1] in (0xC0, 0xC2):
                h = struct.unpack(">H", data[i + 5:i + 7])[0]
                w = struct.unpack(">H", data[i + 7:i + 9])[0]
                return w, h
            i += 1
        return 1920, 1080

    def run_ocr(self, image_bytes: bytes, search_text: str = "") -> dict:
        img_w, img_h = self.get_jpeg_dimensions(image_bytes)
        result = {
            "width": img_w,
            "height": img_h,
            "elements": [],
            "tesseract_found": self.tesseract_bin is not None,
        }

        if self.tesseract_bin is None:
            result["error"] = "Tesseract OCR binary not found."
            return result

        pil_img = PILImage.open(io.BytesIO(image_bytes))
        try:
            data = pytesseract.image_to_data(pil_img, output_type=pytesseract.Output.DICT)
        except Exception as e:
            result["error"] = f"Tesseract error: {e}"
            return result

        elements = []
        search_lower = search_text.strip().lower() if search_text else ""

        for i in range(len(data["text"])):
            word = data["text"][i].strip()
            if not word:
                continue
            conf = float(data["conf"][i]) if data["conf"][i] not in ("", "-1") else 0.0
            if conf < 30:
                continue
            if search_lower and search_lower not in word.lower():
                continue
            x = int(data["left"][i])
            y = int(data["top"][i])
            w = int(data["width"][i])
            h = int(data["height"][i])
            cx = x + w // 2
            cy = y + h // 2
            elements.append({
                "text": word,
                "confidence": round(conf, 1),
                "x_pct": round(cx / img_w * 100, 1),
                "y_pct": round(cy / img_h * 100, 1),
                "pixel": [cx, cy],
                "box": [x, y, w, h],
            })

        elements.sort(key=lambda e: (-e["confidence"], e["y_pct"], e["x_pct"]))
        result["elements"] = elements
        return result
