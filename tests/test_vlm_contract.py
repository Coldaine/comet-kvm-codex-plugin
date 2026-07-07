import unittest
from src.bios_sidecar.perception.vlm_client import VLMClient

class TestVLMContract(unittest.TestCase):
    def setUp(self):
        # Instantiate VLM Client in mock mode
        self.vlm = VLMClient(provider="mock")

    def test_mock_screens_are_stable(self):
        # Giving identical image bytes always yields the exact same mock screen title
        image1 = b"some_stable_image_bytes_here"

        res1 = self.vlm.parse_screenshot(image1)
        res2 = self.vlm.parse_screenshot(image1)

        self.assertEqual(res1["screen_title"], res2["screen_title"])
        self.assertEqual(res1["blocklist_flag"], res2["blocklist_flag"])

    def test_vlm_schema_validation(self):
        valid_res = {
            "screen_title": "EZ Mode",
            "menu_path": ["EZ Mode"],
            "cursor_at": 0,
            "entries": [
                {"label": "CPU Cooler", "type": "leaf-enum", "value": "Water Cooler", "options": ["Water"], "key_to_enter": "Enter"}
            ],
            "blocklist_flag": False,
            "blocklist_keywords": []
        }
        self.assertTrue(self.vlm._validate_vlm_schema(valid_res))

        invalid_res = {
            "screen_title": "EZ Mode",
            "entries": "not_a_list"
        }
        self.assertFalse(self.vlm._validate_vlm_schema(invalid_res))

if __name__ == "__main__":
    unittest.main()
