"""
Tests for VLM client provider routing (offline-safe).

Validates the framework-decision behavior (D10):
- `mock` provider returns deterministic canned parses without any network.
- Key-required providers (openrouter/openai) fall back to mock when no key is set.
- Local providers (ollama/vllm) do NOT require a key.
- Env-driven provider/model resolution works.
"""
from __future__ import annotations

import asyncio
import os
import unittest

from src.bios_sidecar.perception.vlm_client import VLMClient


def _run(coro):
    return asyncio.run(coro)


class VLMRoutingTest(unittest.TestCase):
    def test_mock_default_is_deterministic(self):
        client = VLMClient(provider="mock")
        try:
            a = _run(client.parse_screenshot(b"same-bytes"))
            b = _run(client.parse_screenshot(b"same-bytes"))
        finally:
            _run(client.close())
        self.assertEqual(a["screen_title"], b["screen_title"])
        self.assertIn("entries", a)

    def test_key_required_provider_without_key_falls_back_to_mock(self):
        # openrouter requires a key; with none present it must not attempt a call.
        client = VLMClient(provider="openrouter", api_key=None)
        # Ensure no ambient key leaks in from the environment for this assertion.
        client.api_key = None
        try:
            res = _run(client.parse_screenshot(b"bytes"))
        finally:
            _run(client.close())
        self.assertIn("screen_title", res)  # mock shape

    def test_local_provider_does_not_require_key(self):
        client = VLMClient(provider="ollama")
        try:
            self.assertFalse(client._requires_key())
        finally:
            _run(client.close())

    def test_env_driven_provider_and_model(self):
        os.environ["VLM_PROVIDER"] = "ollama"
        os.environ["VLM_MODEL"] = "ollama/llama3.2-vision"
        try:
            client = VLMClient()
            self.assertEqual(client.provider, "ollama")
            self.assertEqual(client.model, "ollama/llama3.2-vision")
            _run(client.close())
        finally:
            os.environ.pop("VLM_PROVIDER", None)
            os.environ.pop("VLM_MODEL", None)

    def test_default_model_per_provider(self):
        client = VLMClient(provider="ollama")
        try:
            self.assertTrue(client._default_model().startswith("ollama/"))
        finally:
            _run(client.close())

    def test_extract_json_strips_code_fences(self):
        fenced = '```json\n{"screen_title": "X", "entries": []}\n```'
        parsed = VLMClient._extract_json(fenced)
        self.assertEqual(parsed["screen_title"], "X")


if __name__ == "__main__":
    unittest.main(verbosity=2)
