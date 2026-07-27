from __future__ import annotations

import asyncio
import contextlib

import pytest

import httpx
from src.bios_sidecar.perception.vlm_client import VLMClient
from tests.local_services import OpenAICompatibleService


def run(coro):
    return asyncio.run(coro)


def close_client(client: VLMClient) -> None:
    """Close a client's transport, tolerating an already-closed event loop.

    Every test drives its own asyncio.run() loop, so the httpx client is bound to
    a loop that is already gone by the time the `finally` runs. The resulting
    "Event loop is closed" RuntimeError would otherwise mask real assertion
    failures raised from the try block.
    """
    with contextlib.suppress(RuntimeError):
        run(client.close())


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
        close_client(client)


def test_key_required_provider_without_key_fails_closed(monkeypatch):
    # Hermetic: without this, a dev machine with Doppler resolves a REAL key and
    # this test fires live HTTPS requests at openrouter.ai.
    from src.kvm_core import doppler_credentials as dc

    monkeypatch.delenv("VLM_API_KEY", raising=False)
    monkeypatch.setattr(dc, "resolve_vlm_api_key", lambda *, require=False: None)

    client = VLMClient(provider="openrouter", api_key=None)
    try:
        client.api_key = None
        with pytest.raises(RuntimeError, match="VLM_API_KEY is required"):
            run(client.parse_screenshot(b"bytes"))
    finally:
        close_client(client)


@pytest.mark.parametrize(
    ("provider", "expected_base_url", "expected_model"),
    [
        ("openai", "https://api.openai.com/v1", "gpt-4o"),
        ("openrouter", "https://openrouter.ai/api/v1", "openrouter/free"),
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
        close_client(client)


def test_provider_prefix_is_not_sent_to_openai_compatible_endpoint():
    client = VLMClient(provider="ollama", model="ollama/llama3.2-vision")
    try:
        assert client._resolved_model() == "llama3.2-vision"
    finally:
        close_client(client)


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
            close_client(client)


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
            close_client(client)


def test_invalid_vlm_provider_raises_value_error():
    client = VLMClient(provider="invalid-provider")
    try:
        with pytest.raises(ValueError, match="Unsupported provider"):
            run(client.parse_screenshot(b"image"))
    finally:
        close_client(client)


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
        close_client(client)


def test_mock_vlm_tolerates_cold_runtime_without_autoconnect(monkeypatch):
    """Managed lifecycle: the mock guard must not force a connect just to look."""

    class ColdKVM:
        client = None

        def __init__(self) -> None:
            self.ensure_calls = 0

        async def ensure_connected(self, target=None):
            self.ensure_calls += 1
            raise AssertionError(
                "the VLM live-refusal guard must never trigger a connection"
            )

    kvm = ColdKVM()

    import src.kvm_core.runtime
    monkeypatch.setattr(src.kvm_core.runtime, "get_kvm_runtime", lambda: kvm)

    client = VLMClient(provider="mock")
    try:
        result = run(client.parse_screenshot(b"image"))
        assert result["screen_title"]
        assert kvm.ensure_calls == 0
    finally:
        close_client(client)


def test_vlm_guard_reads_only_client_attribute(monkeypatch):
    """The guard may read `kvm.client` and nothing else off the runtime."""

    class FakeClient:
        host = "127.0.0.1"
        base_url = "https://127.0.0.1"

        def is_connected(self):
            return True

    class OnlyClientKVM:
        client = FakeClient()

        def __getattr__(self, name):
            raise AssertionError(
                f"the VLM guard must read only kvm.client; it touched {name!r}"
            )

    import src.kvm_core.runtime
    monkeypatch.setattr(src.kvm_core.runtime, "get_kvm_runtime", lambda: OnlyClientKVM())

    client = VLMClient(provider="mock")
    try:
        result = run(client.parse_screenshot(b"image"))
        assert result["screen_title"]
    finally:
        close_client(client)


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
        close_client(client)
