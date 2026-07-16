from __future__ import annotations

import asyncio
import pytest

import httpx
from src.bios_sidecar.perception.vlm_client import VLMClient
from tests.local_services import OpenAICompatibleService


def run(coro):
    return asyncio.run(coro)


def install_mock_transport(
    client: VLMClient,
    handler,
) -> None:
    run(client.client.aclose())
    client.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_provider_is_required_instead_of_fabricating_a_parse():
    client = VLMClient(provider="")
    try:
        with pytest.raises(RuntimeError, match="VLM_PROVIDER is required"):
            run(client.parse_screenshot(b"bytes"))
    finally:
        run(client.close())


def test_key_required_provider_without_key_fails_closed():
    client = VLMClient(provider="openrouter", api_key=None)
    try:
        client.api_key = None
        with pytest.raises(RuntimeError, match="VLM_API_KEY is required"):
            run(client.parse_screenshot(b"bytes"))
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
    response = {
            "screen_title": "Main",
            "menu_path": ["Main"],
            "cursor_at": 0,
            "entries": [],
            "blocklist_flag": False,
            "blocklist_keywords": [],
    }
    with OpenAICompatibleService() as service:
        service.enqueue_parse(response)
        client = VLMClient(
            provider="ollama",
            model="ollama/test-model",
            base_url=service.base_url,
        )
        try:
            result = run(client.parse_screenshot(b"image"))
            assert result["screen_title"] == "Main"
            captured = service.requests[0]
            assert captured["model"] == "test-model"
            assert captured["response_format"] == {"type": "json_object"}
            assert captured["messages"][1]["content"][1]["type"] == "image_url"
        finally:
            run(client.close())


def test_local_provider_retries_without_response_format():
    response = {
            "screen_title": "Main",
            "menu_path": [],
            "cursor_at": None,
            "entries": [],
            "blocklist_flag": False,
            "blocklist_keywords": [],
    }
    with OpenAICompatibleService() as service:
        service.enqueue_payload(400, {"error": "unsupported"})
        service.enqueue_parse(response)
        client = VLMClient(provider="vllm", base_url=service.base_url)
        try:
            assert run(client.parse_screenshot(b"image"))["screen_title"] == "Main"
            assert len(service.requests) == 2
            assert "response_format" in service.requests[0]
            assert "response_format" not in service.requests[1]
        finally:
            run(client.close())


def test_invalid_vlm_provider_raises_value_error():
    client = VLMClient(provider="invalid-provider")
    try:
        with pytest.raises(ValueError, match="Unsupported provider"):
            run(client.parse_screenshot(b"image"))
    finally:
        run(client.close())


def test_mock_vlm_on_live_comet_fails_closed(monkeypatch):
    class FakeClient:
        host = "192.168.0.126"
        base_url = "https://192.168.0.126"
        def is_connected(self):
            return True

    class FakeKVM:
        client = FakeClient()

    import src.kvm_core.runtime
    monkeypatch.setattr(src.kvm_core.runtime, "get_kvm_runtime", lambda: FakeKVM())

    client = VLMClient(provider="mock")
    try:
        with pytest.raises(RuntimeError, match="refusing to run bios_\\* tools on fabricated VLM output"):
            run(client.parse_screenshot(b"image"))
    finally:
        run(client.close())


def test_vlm_provider_failure_returns_unparseable_state():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal Server Error")

    client = VLMClient(provider="ollama")
    install_mock_transport(client, handler)
    try:
        res = run(client.parse_screenshot(b"image"))
        assert res["screen_title"] == "Unparseable Screen"
        assert res["entries"] == []
    finally:
        run(client.close())
