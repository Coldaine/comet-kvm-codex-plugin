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


def test_codex_runs_hermetically_with_pinned_model(monkeypatch):
    # No VLM_MODEL -> the provider pins its own default, because
    # --ignore-user-config means ~/.codex/config.toml can't supply one.
    monkeypatch.delenv("VLM_MODEL", raising=False)
    monkeypatch.delenv("VLM_CODEX_EFFORT", raising=False)
    captured: dict[str, list[str]] = {}

    async def fake_run(cmd, stdin_text, env):
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
        assert cmd[cmd.index("-m") + 1] == "gpt-5.6-sol"
        # The user's config must not leak into the transcriber: their notify
        # hook would spawn a program per parse and their plugins would load.
        assert "--ignore-user-config" in cmd
        assert '-c' in cmd and 'model_reasoning_effort="medium"' in cmd
        assert "--ephemeral" in cmd
        assert "--output-schema" in cmd
        assert "-s" in cmd and cmd[cmd.index("-s") + 1] == "read-only"
        # The image lands in a temp file passed via -i, encoded from our bytes.
        img_path = cmd[cmd.index("-i") + 1]
        assert img_path.endswith("screen.jpg")
    finally:
        close_client(client)


def test_codex_effort_is_overridable(monkeypatch):
    monkeypatch.setenv("VLM_CODEX_EFFORT", "low")
    captured: dict[str, list[str]] = {}

    async def fake_run(cmd, stdin_text, env):
        captured["cmd"] = cmd
        Path(cmd[cmd.index("-o") + 1]).write_text(json.dumps(_VALID_PARSE), encoding="utf-8")
        return ("", "", 0)

    monkeypatch.setattr(VLMClient, "_run_codex", staticmethod(fake_run))
    monkeypatch.setattr("shutil.which", lambda name: "C:/fake/codex.exe")

    client = VLMClient(provider="codex")
    try:
        run(client.parse_screenshot(b"jpegbytes"))
        assert 'model_reasoning_effort="low"' in captured["cmd"]
    finally:
        close_client(client)


def test_codex_child_env_cannot_reroute_billing_to_an_api_key(monkeypatch):
    # A stray OPENAI_API_KEY in the server env must never silently move parses
    # off the user's ChatGPT subscription and onto metered API billing.
    monkeypatch.setenv("OPENAI_API_KEY", "sk-should-not-propagate")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.invalid/v1")
    seen: dict[str, dict[str, str]] = {}

    async def fake_run(cmd, stdin_text, env):
        seen["env"] = env
        Path(cmd[cmd.index("-o") + 1]).write_text(json.dumps(_VALID_PARSE), encoding="utf-8")
        return ("", "", 0)

    monkeypatch.setattr(VLMClient, "_run_codex", staticmethod(fake_run))
    monkeypatch.setattr("shutil.which", lambda name: "C:/fake/codex.exe")

    client = VLMClient(provider="codex")
    try:
        run(client.parse_screenshot(b"jpegbytes"))
        assert "OPENAI_API_KEY" not in seen["env"]
        assert "OPENAI_BASE_URL" not in seen["env"]
        # ...but the child still gets a usable environment to launch with.
        assert seen["env"], "child env must not be emptied wholesale"
    finally:
        close_client(client)


def test_codex_explicit_model_is_passed_through(monkeypatch):
    captured: dict[str, list[str]] = {}

    async def fake_run(cmd, stdin_text, env):
        captured["cmd"] = cmd
        Path(cmd[cmd.index("-o") + 1]).write_text(json.dumps(_VALID_PARSE), encoding="utf-8")
        return ("", "", 0)

    monkeypatch.setattr(VLMClient, "_run_codex", staticmethod(fake_run))
    monkeypatch.setattr("shutil.which", lambda name: "C:/fake/codex.exe")

    client = VLMClient(provider="codex", model="gpt-5.6-thinking")
    try:
        run(client.parse_screenshot(b"jpegbytes"))
        cmd = captured["cmd"]
        assert cmd[cmd.index("-m") + 1] == "gpt-5.6-thinking"
    finally:
        close_client(client)


def test_codex_image_bytes_round_trip(monkeypatch):
    payload = b"\xff\xd8fake-jpeg-bytes"
    seen: dict[str, bytes] = {}

    async def fake_run(cmd, stdin_text, env):
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
    async def fake_run(cmd, stdin_text, env):
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

