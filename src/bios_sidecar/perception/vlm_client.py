from __future__ import annotations
import os
import json
import logging
import base64
from typing import Optional, Dict, Any
import httpx
from src.bios_sidecar.perception.contract import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE, VLM_DEFAULT_PARAMS

LOG = logging.getLogger("bios_sidecar.perception.vlm")

class VLMClient:
    def __init__(self, api_key: Optional[str] = None, provider: str = "mock"):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY") or os.environ.get("VLM_API_KEY")
        self.provider = provider
        self.client = httpx.AsyncClient(timeout=30.0)

    async def close(self) -> None:
        await self.client.aclose()

    async def __aenter__(self) -> VLMClient:
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        await self.close()

    async def parse_screenshot(
        self,
        image_bytes: bytes,
        previous_state: Optional[Dict[str, Any]] = None,
        last_action: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Parses screenshot using chosen VLM provider.
        Supports automatic Corrective Retry according to contract:
        - 1st retry: corrective prompt.
        - 2nd retry: fresh prompt.
        - 3rd: marks unparseable fallback.
        """
        if self.provider == "mock" or not self.api_key:
            return self._parse_mock(image_bytes)

        # Build prompts
        system_prompt = SYSTEM_PROMPT
        user_prompt = USER_PROMPT_TEMPLATE

        # Add hints to user prompt if provided
        hints = []
        if previous_state:
            hints.append(f"Previous screen title was: {previous_state.get('location', {}).get('screen_title')}")
        if last_action:
            hints.append(f"Last keystroke executed was: {last_action}")
        if hints:
            user_prompt += "\n\nHints:\n" + "\n".join(hints)

        image_b64 = base64.b64encode(image_bytes).decode("utf-8")

        for attempt in range(3):
            try:
                if attempt == 0:
                    current_user_prompt = user_prompt
                elif attempt == 1:
                    # Corrective prompt retry
                    current_user_prompt = (
                        user_prompt
                        + "\n\nYour previous response was not valid JSON or was missing required fields."
                        " Return only the JSON object matching the schema."
                    )
                    LOG.info("VLM corrective retry (attempt 2)")
                else:
                    # Fresh original query retry
                    current_user_prompt = user_prompt
                    LOG.info("VLM fresh rerun retry (attempt 3)")

                response_parsed = await self._call_api(system_prompt, current_user_prompt, image_b64)
                if self._validate_vlm_schema(response_parsed):
                    return response_parsed
                else:
                    LOG.warning("VLM response failed schema checks.")
            except Exception as e:
                LOG.error("VLM call attempt %d failed: %s", attempt + 1, e)

        # Fallback if all retries fail
        LOG.error("VLM failed after 3 attempts. Returning unparseable state.")
        return {
            "screen_title": "Unparseable Screen",
            "menu_path": [],
            "cursor_at": None,
            "entries": [],
            "blocklist_flag": False,
            "blocklist_keywords": [],
        }

    async def _call_api(self, sys: str, user: str, img_b64: str) -> Dict[str, Any]:
        """Performs actual HTTP call to the hosted API."""
        if self.provider == "openai":
            url = "https://api.openai.com/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            body = {
                "model": "gpt-4o",
                "messages": [
                    {"role": "system", "content": sys},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": user},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
                        ],
                    },
                ],
                "temperature": VLM_DEFAULT_PARAMS["temperature"],
                "max_tokens": VLM_DEFAULT_PARAMS["max_tokens"],
                "response_format": VLM_DEFAULT_PARAMS["response_format"],
            }
            r = await self.client.post(url, headers=headers, json=body)
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"]
            return json.loads(content)
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

    def _validate_vlm_schema(self, res: Any) -> bool:
        """Lightweight check to make sure the dict matches the schema."""
        if not isinstance(res, dict):
            return False
        required_keys = ["screen_title", "menu_path", "cursor_at", "entries", "blocklist_flag", "blocklist_keywords"]
        if not all(k in res for k in required_keys):
            return False
        if not isinstance(res["entries"], list):
            return False
        for e in res["entries"]:
            if not isinstance(e, dict) or "label" not in e or "type" not in e:
                return False
        return True

    def _parse_mock(self, img_bytes: bytes) -> Dict[str, Any]:
        """Generates predictable mockup data for testing, hashing the image to stay idempotent."""
        import hashlib
        h = hashlib.sha256(img_bytes).hexdigest()

        # Consistent mock screens based on suffix of hash
        val = int(h[:4], 16) % 4

        if val == 0:
            return {
                "screen_title": "EZ Mode",
                "menu_path": ["EZ Mode"],
                "cursor_at": 0,
                "entries": [
                    {"label": "CPU Cooler Tuning", "type": "leaf-enum", "value": "Water Cooler", "options": ["Box Cooler", "Tower Cooler", "Water Cooler"], "key_to_enter": "Enter"},
                    {"label": "Memory Fast Boot", "type": "leaf-toggle", "value": "Enabled", "options": ["Enabled", "Disabled"], "key_to_enter": "Enter"},
                ],
                "blocklist_flag": False,
                "blocklist_keywords": [],
            }
        elif val == 1:
            return {
                "screen_title": "Advanced SETTINGS",
                "menu_path": ["SETTINGS"],
                "cursor_at": 1,
                "entries": [
                    {"label": "System Status", "type": "submenu", "value": None, "options": None, "key_to_enter": "Enter"},
                    {"label": "Advanced", "type": "submenu", "value": None, "options": None, "key_to_enter": "Enter"},
                    {"label": "Boot", "type": "submenu", "value": None, "options": None, "key_to_enter": "Enter"},
                    {"label": "Security", "type": "submenu", "value": None, "options": None, "key_to_enter": "Enter"},
                ],
                "blocklist_flag": False,
                "blocklist_keywords": [],
            }
        elif val == 2:
            return {
                "screen_title": "Advanced",
                "menu_path": ["SETTINGS", "Advanced"],
                "cursor_at": 2,
                "entries": [
                    {"label": "PCI Subsystem Settings", "type": "submenu", "value": None, "options": None, "key_to_enter": "Enter"},
                    {"label": "ACPI Settings", "type": "submenu", "value": None, "options": None, "key_to_enter": "Enter"},
                    {"label": "Integrated Peripherals", "type": "submenu", "value": None, "options": None, "key_to_enter": "Enter"},
                ],
                "blocklist_flag": False,
                "blocklist_keywords": [],
            }
        else:
            return {
                "screen_title": "PCI Subsystem Settings",
                "menu_path": ["SETTINGS", "Advanced", "PCI Subsystem Settings"],
                "cursor_at": 1,
                "entries": [
                    {"label": "Above 4G memory/Crypto Currency mining", "type": "leaf-toggle", "value": "Enabled", "options": ["Enabled", "Disabled"], "key_to_enter": "Enter"},
                    {"label": "Re-Size BAR Support", "type": "leaf-enum", "value": "Auto", "options": ["Auto", "Disabled", "Enabled"], "key_to_enter": "Enter"},
                ],
                "blocklist_flag": False,
                "blocklist_keywords": [],
            }
