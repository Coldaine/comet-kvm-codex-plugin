import unittest
from PIL import Image as PILImage
import io
from src.bios_sidecar.state.hashing import calculate_visual_phash, calculate_ocr_hash, calculate_state_semantic_hash, hamming_distance

def create_mock_jpeg(add_diff: bool = False) -> bytes:
    img = PILImage.new("RGB", (100, 100))
    for x in range(100):
        for y in range(100):
            if add_diff:
                img.putpixel((x, y), (x * 2, y, (x + y) % 256))
            else:
                img.putpixel((x, y), (x, (y * 3) % 256, (x - y) % 256))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()

class TestStateIdentity(unittest.TestCase):
    def test_phash_differentiation(self):
        # Generate two different mock images
        blue_img = create_mock_jpeg(add_diff=False)
        red_img = create_mock_jpeg(add_diff=True)

        blue_hash = calculate_visual_phash(blue_img)
        red_hash = calculate_visual_phash(red_img)

        # Self hashes are identical
        self.assertEqual(blue_hash, calculate_visual_phash(blue_img))

        # Blue and Red are visually different, so hashes and hamming distances should differ
        self.assertNotEqual(blue_hash, red_hash)
        dist = hamming_distance(blue_hash, red_hash)
        self.assertTrue(dist > 0)

    def test_ocr_text_hashing_is_stable(self):
        ocr_elements_1 = [{"text": "Hello"}, {"text": "World"}]
        ocr_elements_2 = [{"text": "World"}, {"text": "Hello"}] # shuffle order

        hash1 = calculate_ocr_hash(ocr_elements_1)
        hash2 = calculate_ocr_hash(ocr_elements_2)

        # Output hash is normalized and sorted, so original ordering shuffling does not matter!
        self.assertEqual(hash1, hash2)

    def test_semantic_hash_reproducibility(self):
        sem1 = calculate_state_semantic_hash("msi", "z690", "Main Settings", ["SETTINGS", "Advanced"])
        sem2 = calculate_state_semantic_hash("MSI", "Z690", "Main Settings", ["SETTINGS", "Advanced"]) # case difference
        self.assertEqual(sem1, sem2)

    def test_invalid_image_fallback_is_input_specific(self):
        hash1 = calculate_visual_phash(b"not an image")
        hash2 = calculate_visual_phash(b"also not an image")
        self.assertEqual(hash1, calculate_visual_phash(b"not an image"))
        self.assertNotEqual(hash1, hash2)

if __name__ == "__main__":
    unittest.main()
