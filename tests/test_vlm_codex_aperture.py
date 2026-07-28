"""Offline tests for the codex (scripted sub-agent) and aperture VLM providers."""
from __future__ import annotations

import asyncio
import base64
import contextlib
import json
from pathlib import Path

import pytest

from src.bios_sidecar.perception.vlm_client import VLMClient

_VALID_PARSE = {
    "screen_title": "Settings",
    "menu_path": ["Settings"],
    "cursor_at": 0,
    "entries": [
        {"label": "Advanced", "type": "submenu", "value": None,
         "options": None, "key_to_enter": "Enter"},
    ],
    "blocklist_flag": False,
    "blocklist_keywords": [],
}


def run(coro):
    return asyncio.run(coro)


def close_client(client: VLMClient) -> None:
    with contextlib.suppress(RuntimeError):
        run(client.close())


# --- codex provider --------------------------------------------------------


def test_codex_provider_requires_no_api_key(monkeypatch):
    monkeypatch.delenv("VLM_API_KEY", raising=False)
    client = VLMClient(provider="codex", api_key=None)
    try:
        assert client._requires_key() is False
        client._validate_configuration()  # must not raise about keys
    finally:
        close_client(client)


def test_codex_empty_model_is_valid_and_omits_model_flag(monkeypatch):
    # No VLM_MODEL -> `codex exec` inherits ~/.codex/config.toml defaults.
    monkeypatch.delenv("VLM_MODEL", raising=False)
    captured: dict[str, list[str]] = {}

    async def fake_run(cmd, stdin_text):
        captured["cmd"] = cmd
        out_path = Path(cmd[cmd.index("-o") + 1])
        out_path.write_text(json.dumps(_VALID_PARSE), encoding="utf-8")
        return ("", "", 0)

    monkeypatch.setattr(VLMClient, "_run_codex", staticmethod(fake_run))
    monkeypatch.setattr("shutil.which", lambda name: "C:/fake/codex.exe")

    client = VLMClient(provider="codex")
    try:
        result = run(client.parse_screenshot(b"jpegbytes"))
        assert result["screen_title"] == "Settings"
        cmd = captured["cmd"]
        assert "-m" not in cmd
        assert "--ephemeral" in cmd
        assert "--output-schema" in cmd
        assert "-s" in cmd and cmd[cmd.index("-s") + 1] == "read-only"
        # The image lands in a temp file passed via -i, encoded from our bytes.
        img_path = cmd[cmd.index("-i") + 1]
        assert img_path.endswith("screen.jpg")
    finally:
        close_client(client)


def test_codex_explicit_model_is_passed_through(monkeypatch):
    captured: dict[str, list[str]] = {}

    async def fake_run(cmd, stdin_text):
        captured["cmd"] = cmd
        Path(cmd[cmd.index("-o") + 1]).write_text(json.dumps(_VALID_PARSE), encoding="utf-8")
        return ("", "", 0)

    monkeypatch.setattr(VLMClient, "_run_codex", staticmethod(fake_run))
    monkeypatch.setattr("shutil.which", lambda name: "C:/fake/codex.exe")

    client = VLMClient(provider="codex", model="gpt-5.6-sol")
    try:
        run(client.parse_screenshot(b"jpegbytes"))
        cmd = captured["cmd"]
        assert cmd[cmd.index("-m") + 1] == "gpt-5.6-sol"
    finally:
        close_client(client)


def test_codex_image_bytes_round_trip(monkeypatch):
    payload = b"\xff\xd8fake-jpeg-bytes"
    seen: dict[str, bytes] = {}

    async def fake_run(cmd, stdin_text):
        seen["image"] = Path(cmd[cmd.index("-i") + 1]).read_bytes()
        Path(cmd[cmd.index("-o") + 1]).write_text(json.dumps(_VALID_PARSE), encoding="utf-8")
        return ("", "", 0)

    monkeypatch.setattr(VLMClient, "_run_codex", staticmethod(fake_run))
    monkeypatch.setattr("shutil.which", lambda name: "C:/fake/codex.exe")

    client = VLMClient(provider="codex")
    try:
        run(client.parse_screenshot(payload))
        assert seen["image"] == payload
    finally:
        close_client(client)


def test_codex_missing_cli_fails_with_actionable_error(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    client = VLMClient(provider="codex")
    try:
        with pytest.raises(RuntimeError, match="Codex CLI"):
            run(client._call_codex("sys", "user", base64.b64encode(b"x").decode()))
    finally:
        close_client(client)


def test_codex_nonzero_exit_surfaces_stderr(monkeypatch):
    async def fake_run(cmd, stdin_text):
        return ("", "login required", 1)

    monkeypatch.setattr(VLMClient, "_run_codex", staticmethod(fake_run))
    monkeypatch.setattr("shutil.which", lambda name: "C:/fake/codex.exe")

    client = VLMClient(provider="codex")
    try:
        with pytest.raises(RuntimeError, match="login required"):
            run(client._call_codex("sys", "user", base64.b64encode(b"x").decode()))
    finally:
        close_client(client)


# --- aperture provider -----------------------------------------------------


def test_aperture_defaults_and_no_key_required(monkeypatch):
    monkeypatch.delenv("VLM_API_KEY", raising=False)
    monkeypatch.delenv("VLM_MODEL", raising=False)
    monkeypatch.delenv("VLM_BASE_URL", raising=False)
    client = VLMClient(provider="aperture")
    try:
        assert client._requires_key() is False
        assert "aperture-gateway" in client.base_url
        # Gateway model FQNs keep their provider prefix intact.
        assert client._resolved_model() == "gemini-oai/gemini-3.5-flash"
        assert client._response_format()["type"] == "json_schema"
        client._validate_configuration()
    finally:
        close_client(client)

