from __future__ import annotations

import asyncio
import json
from collections.abc import Callable

import httpx
import pytest

from src.bios_sidecar.perception.vlm_client import VLMClient


def run(coro):
    return asyncio.run(coro)


def install_mock_transport(
    client: VLMClient,
    handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    run(client.client.aclose())
    client.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_mock_default_is_deterministic():
    client = VLMClient(provider="mock")
    try:
        assert run(client.parse_screenshot(b"same-bytes")) == run(client.parse_screenshot(b"same-bytes"))
    finally:
        run(client.close())


def test_key_required_provider_without_key_falls_back_to_mock():
    client = VLMClient(provider="openrouter", api_key=None)
    try:
        client.api_key = None
        assert run(client.parse_screenshot(b"bytes"))["screen_title"]
    finally:
        run(client.close())


@pytest.mark.parametrize(
    ("provider", "expected_base_url", "expected_model"),
    [
        ("openai", "https://api.openai.com/v1", "gpt-4o"),
        ("openrouter", "https://openrouter.ai/api/v1", "qwen/qwen2.5-vl-72b-instruct"),
        ("ollama", "http://localhost:11434/v1", "llama3.2-vision"),
        ("vllm", "http://localhost:8000/v1", "qwen2.5-vl"),
    ],
)
def test_provider_defaults(provider, expected_base_url, expected_model):
    client = VLMClient(provider=provider)
    try:
        assert client.base_url == expected_base_url
        assert client._resolved_model() == expected_model
    finally:
        run(client.close())


def test_provider_prefix_is_not_sent_to_openai_compatible_endpoint():
    client = VLMClient(provider="ollama", model="ollama/llama3.2-vision")
    try:
        assert client._resolved_model() == "llama3.2-vision"
    finally:
        run(client.close())


def test_extract_json_strips_code_fences():
    assert VLMClient._extract_json('```json\n{"screen_title": "X"}\n```') == {"screen_title": "X"}


def test_openai_compatible_request_uses_schema_and_validates_response():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({
            "screen_title": "Main",
            "menu_path": ["Main"],
            "cursor_at": 0,
            "entries": [],
            "blocklist_flag": False,
            "blocklist_keywords": [],
        })}}]})

    client = VLMClient(provider="ollama", model="ollama/test-model")
    install_mock_transport(client, handler)
    try:
        result = run(client.parse_screenshot(b"image"))
        assert result["screen_title"] == "Main"
        assert captured["model"] == "test-model"
        assert captured["response_format"] == {"type": "json_object"}
        assert captured["messages"][1]["content"][1]["type"] == "image_url"
    finally:
        run(client.close())


def test_local_provider_retries_without_response_format():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append(body)
        if "response_format" in body:
            return httpx.Response(400, json={"error": "unsupported"})
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({
            "screen_title": "Main",
            "menu_path": [],
            "cursor_at": None,
            "entries": [],
            "blocklist_flag": False,
            "blocklist_keywords": [],
        })}}]})

    client = VLMClient(provider="vllm")
    install_mock_transport(client, handler)
    try:
        assert run(client.parse_screenshot(b"image"))["screen_title"] == "Main"
        assert len(requests) == 2
        assert "response_format" in requests[0]
        assert "response_format" not in requests[1]
    finally:
        run(client.close())
