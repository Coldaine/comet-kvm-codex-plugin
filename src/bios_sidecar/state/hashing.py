from __future__ import annotations
import hashlib
from PIL import Image as PILImage
import io

def calculate_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def calculate_visual_phash(image_bytes: bytes) -> str:
    """
    Computes a deterministic visual Difference Hash (dHash) using Pillow.
    Resize image to 9x8, convert to grayscale, and compare adjacent pixels.
    """
    try:
        img = PILImage.open(io.BytesIO(image_bytes))
        # Resize to 9x8 and convert to grayscale (L)
        img_gray = img.resize((9, 8)).convert("L")
        pixels = list(img_gray.get_flattened_data())

        # dHash computation: compare pixel[x] to pixel[x+1] for each row
        difference = []
        for row in range(8):
            for col in range(8):
                idx = row * 9 + col
                pixel_left = pixels[idx]
                pixel_right = pixels[idx + 1]
                difference.append(pixel_left > pixel_right)

        # Convert binary array to hex string
        decimal_val = 0
        hex_string = []
        for index, value in enumerate(difference):
            if value:
                decimal_val += 2 ** (index % 8)
            if (index % 8) == 7:
                hex_string.append(hex(decimal_val)[2:].zfill(2))
                decimal_val = 0
        return "".join(hex_string)
    except Exception:
        return hashlib.sha256(image_bytes).hexdigest()[:16]

def calculate_ocr_hash(ocr_elements: list[dict]) -> str:
    """
    Normalized visible text hash.
    Extract, sort, and hash all visible OCR words.
    """
    words = [e.get("text", "").strip() for e in ocr_elements if e.get("text")]
    normalized = " ".join(sorted(words)).lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

def calculate_state_semantic_hash(vendor: str, board_hint: str, screen_title: str, menu_path: list[str]) -> str:
    """Combines high-level semantic tokens to form a stable string hash."""
    path_str = " > ".join(menu_path)
    combined = f"{vendor}:{board_hint}:{screen_title}:{path_str}".lower()
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()

def hamming_distance(hex1: str, hex2: str) -> int:
    """Computes the bitwise Hamming distance between two hex hashes of equal length."""
    if len(hex1) != len(hex2):
        return 999
    try:
        val1 = int(hex1, 16)
        val2 = int(hex2, 16)
        diff = val1 ^ val2
        return bin(diff).count("1")
    except ValueError:
        return 999
