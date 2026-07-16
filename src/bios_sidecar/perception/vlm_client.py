from __future__ import annotations

import base64
import json
import logging
import os
from typing import Any, Optional

import httpx

from src.bios_sidecar.perception.contract import (
    SYSTEM_PROMPT,
    USER_PROMPT_TEMPLATE,
    VLM_DEFAULT_PARAMS,
)
from src.bios_sidecar.perception.models import BiosScreenParse

LOG = logging.getLogger("bios_sidecar.perception.vlm")
_KEY_REQUIRED_PROVIDERS = frozenset({"openrouter", "openai"})
_PROVIDER_DEFAULTS = {
    "openai": ("https://api.openai.com/v1", "gpt-4o"),
    "openrouter": ("https://openrouter.ai/api/v1", "qwen/qwen2.5-vl-72b-instruct"),
    "ollama": ("http://localhost:11434/v1", "llama3.2-vision"),
    "vllm": ("http://localhost:8000/v1", "qwen2.5-vl"),
}


class VLMClient:
    """Small OpenAI-compatible vision client.

    This deliberately uses httpx rather than LiteLLM/instructor: every supported
    remote or local provider exposes the same chat-completions contract needed by
    the sidecar. Pydantic validates the returned JSON locally.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> None:
        self.provider = (provider or os.environ.get("VLM_PROVIDER", "mock")).lower()
        self.api_key = api_key or os.environ.get("VLM_API_KEY")
        self.model = model or os.environ.get("VLM_MODEL")
        self.base_url = (base_url or os.environ.get("VLM_BASE_URL") or self._default_base_url()).rstrip("/")
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0))

    def _requires_key(self) -> bool:
        return self.provider in _KEY_REQUIRED_PROVIDERS

    def _default_base_url(self) -> str:
        return _PROVIDER_DEFAULTS.get(self.provider, ("", ""))[0]

    def _default_model(self) -> str:
        return _PROVIDER_DEFAULTS.get(self.provider, ("", ""))[1]

    def _resolved_model(self) -> str:
        model = self.model or self._default_model()
        if not model:
            raise ValueError(f"VLM_MODEL is required for provider: {self.provider}")
        return model.removeprefix(f"{self.provider}/")

    async def close(self) -> None:
        await self.client.aclose()

    async def __aenter__(self) -> "VLMClient":
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        await self.close()

    async def parse_screenshot(
        self,
        image_bytes: bytes,
        previous_state: Optional[dict[str, Any]] = None,
        last_action: Optional[str] = None,
    ) -> dict[str, Any]:
        if self.provider == "mock" or (self._requires_key() and not self.api_key):
            return self._parse_mock(image_bytes)

        user_prompt = self._build_user_prompt(previous_state, last_action)
        image_b64 = base64.b64encode(image_bytes).decode("ascii")
        for attempt in range(3):
            prompt = user_prompt
            if attempt >= 1:
                prompt += "\n\nYour previous response was invalid. Return only JSON matching the schema."
            try:
                parsed = await self._call_api(SYSTEM_PROMPT, prompt, image_b64)
                return BiosScreenParse.model_validate(parsed).model_dump()
            except Exception as exc:
                LOG.warning("VLM call attempt %d failed: %s", attempt + 1, type(exc).__name__)

        LOG.error("VLM failed after 3 attempts; returning unparseable state")
        return {
            "screen_title": "Unparseable Screen",
            "menu_path": [],
            "cursor_at": None,
            "entries": [],
            "blocklist_flag": False,
            "blocklist_keywords": [],
        }

    @staticmethod
    def _build_user_prompt(
        previous_state: Optional[dict[str, Any]], last_action: Optional[str]
    ) -> str:
        hints: list[str] = []
        if previous_state:
            location = previous_state.get("location")
            if isinstance(location, dict):
                title = location.get("screen_title")
            else:
                title = None
            title = title or previous_state.get("screen_title")
            if title:
                hints.append(f"Previous screen title was: {title}")
        if last_action:
            hints.append(f"Last keystroke executed was: {last_action}")
        return USER_PROMPT_TEMPLATE + ("\n\nHints:\n" + "\n".join(hints) if hints else "")

    async def _call_api(self, system_prompt: str, user_prompt: str, image_b64: str) -> dict[str, Any]:
        if self.provider not in _PROVIDER_DEFAULTS:
            raise ValueError(f"Unsupported provider: {self.provider}")

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        body: dict[str, Any] = {
            "model": self._resolved_model(),
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                    ],
                },
            ],
            "temperature": VLM_DEFAULT_PARAMS["temperature"],
            "max_tokens": VLM_DEFAULT_PARAMS["max_tokens"],
            "response_format": VLM_DEFAULT_PARAMS["response_format"],
        }
        response = await self.client.post(f"{self.base_url}/chat/completions", headers=headers, json=body)
        if response.status_code == 400 and self.provider in {"ollama", "vllm"}:
            body.pop("response_format")
            response = await self.client.post(f"{self.base_url}/chat/completions", headers=headers, json=body)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        return self._extract_json(content)

    @staticmethod
    def _extract_json(content: str) -> dict[str, Any]:
        content = content.strip()
        if content.startswith("```"):
            content = content.split("```", 2)[1]
            if content.lstrip().startswith("json"):
                content = content.lstrip()[4:]
        value = json.loads(content.strip())
        if not isinstance(value, dict):
            raise ValueError("VLM response must be a JSON object")
        return value

    @staticmethod
    def _parse_mock(image_bytes: bytes) -> dict[str, Any]:
        import hashlib

        screen = int(hashlib.sha256(image_bytes).hexdigest()[:4], 16) % 4
        screens = [
            ("EZ Mode", ["EZ Mode"], 0, [
                {"label": "CPU Cooler Tuning", "type": "leaf-enum", "value": "Water Cooler", "options": ["Box Cooler", "Tower Cooler", "Water Cooler"], "key_to_enter": "Enter"},
                {"label": "Memory Fast Boot", "type": "leaf-toggle", "value": "Enabled", "options": ["Enabled", "Disabled"], "key_to_enter": "Enter"},
            ]),
            ("Advanced SETTINGS", ["SETTINGS"], 1, [
                {"label": "System Status", "type": "submenu", "value": None, "options": None, "key_to_enter": "Enter"},
                {"label": "Advanced", "type": "submenu", "value": None, "options": None, "key_to_enter": "Enter"},
                {"label": "Boot", "type": "submenu", "value": None, "options": None, "key_to_enter": "Enter"},
                {"label": "Security", "type": "submenu", "value": None, "options": None, "key_to_enter": "Enter"},
            ]),
            ("Advanced", ["SETTINGS", "Advanced"], 2, [
                {"label": "PCI Subsystem Settings", "type": "submenu", "value": None, "options": None, "key_to_enter": "Enter"},
                {"label": "ACPI Settings", "type": "submenu", "value": None, "options": None, "key_to_enter": "Enter"},
                {"label": "Integrated Peripherals", "type": "submenu", "value": None, "options": None, "key_to_enter": "Enter"},
            ]),
            ("PCI Subsystem Settings", ["SETTINGS", "Advanced", "PCI Subsystem Settings"], 1, [
                {"label": "Above 4G memory/Crypto Currency mining", "type": "leaf-toggle", "value": "Enabled", "options": ["Enabled", "Disabled"], "key_to_enter": "Enter"},
                {"label": "Re-Size BAR Support", "type": "leaf-enum", "value": "Auto", "options": ["Auto", "Disabled", "Enabled"], "key_to_enter": "Enter"},
            ]),
        ]
        title, path, cursor, entries = screens[screen]
        return {
            "screen_title": title,
            "menu_path": path,
            "cursor_at": cursor,
            "entries": entries,
            "blocklist_flag": False,
            "blocklist_keywords": [],
        }
