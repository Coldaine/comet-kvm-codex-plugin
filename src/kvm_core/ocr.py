from __future__ import annotations
import io
import os
import shutil
import pytesseract
from PIL import Image as PILImage

OCR_TIMEOUT_SECONDS = 15
VALID_PSM_MODES = frozenset({1, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13})


def validate_psm(psm: int) -> None:
    if psm not in VALID_PSM_MODES:
        raise ValueError("psm must be a Tesseract text-recognition mode (1, 3-13 except 2)")


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

    def _ensure_tesseract(self) -> bool:
        if self.tesseract_bin is None:
            # Tesseract may be installed while a long-lived MCP process is running.
            self.tesseract_bin = self._find_tesseract_binary()
            if self.tesseract_bin:
                pytesseract.pytesseract.tesseract_cmd = self.tesseract_bin
        return self.tesseract_bin is not None

    def get_status(self) -> dict:
        return {
            "available": self._ensure_tesseract(),
            "command": self.tesseract_bin or "",
            "timeout_seconds": OCR_TIMEOUT_SECONDS,
        }

    def run_ocr(self, image_bytes: bytes, search_text: str = "", psm: int = 3) -> dict:
        result = {
            "width": 0,
            "height": 0,
            "text": "",
            "lines": [],
            "elements": [],
            "tesseract_found": self.tesseract_bin is not None,
        }

        validate_psm(psm)

        try:
            with PILImage.open(io.BytesIO(image_bytes)) as pil_img:
                img_w, img_h = pil_img.size
                result["width"] = img_w
                result["height"] = img_h

                if not self._ensure_tesseract():
                    result["error"] = "Tesseract OCR binary not found."
                    return result
                result["tesseract_found"] = True

                data = pytesseract.image_to_data(
                    pil_img,
                    config=f"--psm {psm}",
                    lang="eng",
                    output_type=pytesseract.Output.DICT,
                    timeout=OCR_TIMEOUT_SECONDS,
                )
        except Exception as e:
            result["error"] = f"OCR error: {e}"
            return result

        lines: list[str] = []
        current_line = None
        current_words: list[str] = []
        for i, raw_word in enumerate(data["text"]):
            word = raw_word.strip()
            if not word:
                continue
            line_key = (
                data["page_num"][i],
                data["block_num"][i],
                data["par_num"][i],
                data["line_num"][i],
            )
            if current_line is not None and line_key != current_line:
                lines.append(" ".join(current_words))
                current_words = []
            current_line = line_key
            current_words.append(word)
        if current_words:
            lines.append(" ".join(current_words))

        result["lines"] = lines
        result["text"] = "\n".join(lines)

        elements = []
        search_lower = search_text.strip().lower() if search_text else ""

        for i in range(len(data["text"])):
            word = data["text"][i].strip()
            if not word:
                continue
            raw_conf = data["conf"][i]
            conf = float(raw_conf) if raw_conf not in ("", "-1") else 0.0
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

        elements.sort(key=lambda e: (e["y_pct"], e["x_pct"]))
        result["elements"] = elements
        return result

    def run_text_ocr(
        self,
        image_bytes: bytes,
        psm: int = 6,
        languages: str = "",
        crop: tuple[int, int, int, int] | None = None,
    ) -> dict:
        """Return spacing-preserving text without paying for word-box parsing."""
        validate_psm(psm)

        result = {
            "width": 0,
            "height": 0,
            "text": "",
            "lines": [],
            "tesseract_found": self.tesseract_bin is not None,
        }
        try:
            with PILImage.open(io.BytesIO(image_bytes)) as pil_img:
                result["width"], result["height"] = pil_img.size
                if not self._ensure_tesseract():
                    result["error"] = "Tesseract OCR binary not found."
                    return result
                result["tesseract_found"] = True

                ocr_img = pil_img
                cropped_img = None
                if crop is not None:
                    left, top, right, bottom = crop
                    left = max(0, left)
                    top = max(0, top)
                    right = pil_img.width if right < 0 else min(pil_img.width, right)
                    bottom = pil_img.height if bottom < 0 else min(pil_img.height, bottom)
                    if left >= right or top >= bottom:
                        raise ValueError("OCR crop must describe a non-empty region inside the image")
                    cropped_img = pil_img.crop((left, top, right, bottom))
                    ocr_img = cropped_img

                try:
                    text = pytesseract.image_to_string(
                        ocr_img,
                        config=f"--psm {psm} -c preserve_interword_spaces=1",
                        lang=("+".join(languages.replace(",", " ").split()) if languages.strip() else "eng"),
                        timeout=OCR_TIMEOUT_SECONDS,
                    ).rstrip()
                finally:
                    if cropped_img is not None:
                        cropped_img.close()
        except ValueError:
            raise
        except Exception as e:
            result["error"] = f"OCR error: {e}"
            return result

        result["text"] = text
        result["lines"] = text.splitlines()
        return result
