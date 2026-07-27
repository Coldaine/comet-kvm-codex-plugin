"""Red specs for Perception Contract v2.

Spec: docs/superpowers/specs/2026-07-27-perception-contract-v2.md

The VLM stays a transcriber; every new field is advisory input to the Python
policy layer, and risk fields only ever restrict. These tests define:
- BiosScreenParse v2 (bbox/selected/legible, screen_kind, layout, help_text,
  hotkeys, modal, scroll, semantic risk, honest confidence)
- normalize_bios_state consuming all of it
- BiosState/store round-trips preserving the new fields
- VLMClient strict json_schema transport with 400 downgrade ladder,
  the locked-in OpenRouter free default model, and Doppler key fallback
- mock provider emitting v2
"""
from __future__ import annotations

import asyncio
import json

import pytest


def _run(coro):
    return asyncio.run(coro)

from src.bios_sidecar.domain.enums import StateKind
from src.bios_sidecar.perception.models import BiosScreenParse
from src.bios_sidecar.perception.normalize import normalize_bios_state
from src.bios_sidecar.perception.vlm_client import VLMClient


def _normalize(vlm_data: dict, **overrides):
    kwargs = dict(
        run_id="run_test",
        device_id="dev_test",
        vlm_data=vlm_data,
        screenshot_id="shot_1",
        sha256="deadbeef",
        perceptual_hash="phash",
        resolution=[2560, 1440],
        captured_at="2026-07-27T00:00:00",
        ocr_confidence=0.95,
        adapter=None,
    )
    kwargs.update(overrides)
    return normalize_bios_state(**kwargs)


def _v2_parse_dict() -> dict:
    return {
        "screen_title": "Advanced",
        "menu_path": ["SETTINGS", "Advanced"],
        "screen_kind": "setting_list",
        "layout": "list",
        "cursor_at": 1,
        "entries": [
            {
                "label": "PCI Subsystem Settings",
                "type": "submenu",
                "value": None,
                "options": None,
                "key_to_enter": "Enter",
                "selected": False,
                "bbox": [120, 200, 900, 240],
                "legible": True,
            },
            {
                "label": "Re-Size BAR Support",
                "type": "leaf-enum",
                "value": "Auto",
                "options": ["Auto", "Disabled", "Enabled"],
                "key_to_enter": "Enter",
                "selected": True,
                "bbox": [120, 240, 900, 280],
                "legible": False,
            },
        ],
        "help_text": "Enables Resizable BAR support for PCIe devices.",
        "hotkeys": [
            {"key": "F10", "action": "Save & Exit"},
            {"key": "Esc", "action": "Exit"},
        ],
        "modal": {
            "present": False,
            "title": None,
            "message": None,
            "buttons": [],
            "focused_button": None,
        },
        "scroll": {"more_above": False, "more_below": True},
        "risk": {"dangerous": False, "reason": None, "keywords_seen": []},
        "confidence": 0.87,
        "blocklist_flag": False,
        "blocklist_keywords": [],
    }


# --- Parse model -----------------------------------------------------------


def test_v1_parse_dict_still_validates():
    v1 = {
        "screen_title": "Advanced",
        "menu_path": ["SETTINGS", "Advanced"],
        "cursor_at": 0,
        "entries": [
            {"label": "ACPI Settings", "type": "submenu", "value": None,
             "options": None, "key_to_enter": "Enter"},
        ],
        "blocklist_flag": False,
        "blocklist_keywords": [],
    }
    parsed = BiosScreenParse.model_validate(v1)
    assert parsed.entries[0].selected is False
    assert parsed.entries[0].bbox is None
    assert parsed.entries[0].legible is True
    assert parsed.screen_kind is None
    assert parsed.confidence is None


def test_v2_parse_model_roundtrip():
    parsed = BiosScreenParse.model_validate(_v2_parse_dict())
    dumped = parsed.model_dump()
    assert dumped["entries"][1]["selected"] is True
    assert dumped["entries"][1]["bbox"] == [120, 240, 900, 280]
    assert dumped["entries"][1]["legible"] is False
    assert dumped["screen_kind"] == "setting_list"
    assert dumped["layout"] == "list"
    assert dumped["help_text"].startswith("Enables")
    assert dumped["hotkeys"][0] == {"key": "F10", "action": "Save & Exit"}
    assert dumped["modal"]["present"] is False
    assert dumped["scroll"]["more_below"] is True
    assert dumped["risk"]["dangerous"] is False
    assert dumped["confidence"] == pytest.approx(0.87)


# --- normalize: screen_kind ------------------------------------------------


def test_normalize_prefers_vlm_screen_kind():
    data = _v2_parse_dict()
    data["screen_title"] = "Some Vendor Page"  # heuristic would say setting_list
    data["screen_kind"] = "boot_menu"
    state = _normalize(data)
    assert state.location.screen_kind == StateKind.BOOT_MENU


def test_normalize_invalid_screen_kind_falls_back_to_title_heuristic():
    data = _v2_parse_dict()
    data["screen_title"] = "EZ Mode"
    data["screen_kind"] = "not-a-real-kind"
    state = _normalize(data)
    assert state.location.screen_kind == StateKind.EZ_MODE


# --- normalize: entries ----------------------------------------------------


def test_normalize_entry_bbox_selected_legible():
    data = _v2_parse_dict()
    data["cursor_at"] = None  # selection must come from the per-entry flag
    state = _normalize(data)
    assert state.controls[0].bbox == [120, 200, 900, 240]
    assert state.controls[0].selected is False
    assert state.controls[1].selected is True
    assert state.controls[1].legible is False
    assert state.selection.label == "Re-Size BAR Support"
    assert state.selection.bbox == [120, 240, 900, 280]


def test_normalize_cursor_at_still_selects_without_flags():
    data = _v2_parse_dict()
    for e in data["entries"]:
        e.pop("selected")
    data["cursor_at"] = 0
    state = _normalize(data)
    assert state.controls[0].selected is True
    assert state.controls[1].selected is False


# --- normalize: modal ------------------------------------------------------


def test_normalize_modal_metadata_and_restricted_actions():
    data = _v2_parse_dict()
    data["modal"] = {
        "present": True,
        "title": "Save & Exit Setup",
        "message": "Save configuration and exit?",
        "buttons": ["Yes", "No"],
        "focused_button": "No",
    }
    state = _normalize(data)
    assert state.modal.present is True
    assert state.modal.title == "Save & Exit Setup"
    assert state.modal.message == "Save configuration and exit?"
    assert state.modal.options == ["Yes", "No"]
    assert state.modal.focused == "No"
    # A modal's Enter can confirm a save dialog — policy collapses to Escape.
    assert state.actions.safe == ["Escape"]
    assert "Enter" in state.actions.blocked


# --- normalize: risk union -------------------------------------------------


def test_normalize_semantic_risk_unions_blocklist():
    data = _v2_parse_dict()
    data["risk"] = {
        "dangerous": True,
        "reason": "firmware flash utility visible",
        "keywords_seen": ["M-Flash"],
    }
    state = _normalize(data)
    assert state.risk.blocklist_flag is True
    assert state.risk.reason == "firmware flash utility visible"
    assert "M-Flash" in state.risk.blocklist_keywords
    assert "vlm_semantic" in state.risk.hazards
    assert state.actions.safe == ["Escape"]


def test_normalize_semantic_risk_cannot_unblock():
    # VLM saying "not dangerous" must not override the keyword floor.
    data = _v2_parse_dict()
    data["entries"][0]["label"] = "Secure Erase"
    data["risk"] = {"dangerous": False, "reason": None, "keywords_seen": []}
    state = _normalize(data)
    assert state.risk.blocklist_flag is True


# --- normalize: confidence and screen-level extras -------------------------


def test_normalize_real_confidence_passthrough():
    data = _v2_parse_dict()
    data["confidence"] = 0.42
    state = _normalize(data)
    assert state.selection.confidence == pytest.approx(0.42)
    assert state.confidence.vlm == pytest.approx(0.42)


def test_normalize_hotkeys_layout_scroll_help_on_state():
    state = _normalize(_v2_parse_dict())
    assert state.layout == "list"
    assert state.help_text == "Enables Resizable BAR support for PCIe devices."
    assert {"key": "F10", "action": "Save & Exit"} in state.hotkeys
    assert state.scroll == {"more_above": False, "more_below": True}


# --- BiosState round-trips -------------------------------------------------


def test_state_dict_roundtrip_preserves_v2_fields():
    from src.bios_sidecar.domain.models import BiosState

    state = _normalize(_v2_parse_dict())
    restored = BiosState.from_dict(state.to_dict())
    assert restored.layout == state.layout
    assert restored.help_text == state.help_text
    assert restored.hotkeys == state.hotkeys
    assert restored.scroll == state.scroll
    assert restored.controls[1].legible is False


def test_store_persists_v2_extras(tmp_path):
    from src.bios_sidecar.state.store import SQLiteStore

    data = _v2_parse_dict()
    data["modal"] = {
        "present": True,
        "title": "Exit Setup",
        "message": "Discard changes and exit?",
        "buttons": ["Yes", "No"],
        "focused_button": "No",
    }
    state = _normalize(data)

    store = SQLiteStore(str(tmp_path / "map.db"))
    store.save_bios_state(state)
    store._state_cache.clear()  # force a real DB read
    loaded = store.get_bios_state(state.state_id)
    store.close()

    assert loaded is not None
    assert loaded.layout == "list"
    assert loaded.help_text == state.help_text
    assert loaded.hotkeys == state.hotkeys
    assert loaded.scroll == state.scroll
    assert loaded.modal.present is True
    assert loaded.modal.title == "Exit Setup"
    assert loaded.modal.focused == "No"


# --- VLM client transport --------------------------------------------------


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakePoster:
    """Stands in for httpx.AsyncClient; records request bodies."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.bodies = []

    async def post(self, url, headers=None, json=None):
        self.bodies.append(json)
        return self.responses.pop(0)

    async def aclose(self):
        pass


def _chat_payload(content: dict) -> dict:
    return {"choices": [{"message": {"content": json.dumps(content)}}]}


def test_vlm_client_requests_strict_json_schema_for_openrouter():
    client = VLMClient(provider="openrouter", api_key="k", model="m")
    poster = _FakePoster([_FakeResponse(200, _chat_payload(_v2_parse_dict()))])
    client.client = poster
    result = _run(client.parse_screenshot(b"jpegbytes"))
    assert result["screen_title"] == "Advanced"
    rf = poster.bodies[0]["response_format"]
    assert rf["type"] == "json_schema"
    assert "schema" in rf["json_schema"]


def test_vlm_client_downgrades_response_format_on_400():
    client = VLMClient(provider="openrouter", api_key="k", model="m")
    poster = _FakePoster([
        _FakeResponse(400),
        _FakeResponse(200, _chat_payload(_v2_parse_dict())),
    ])
    client.client = poster
    result = _run(client.parse_screenshot(b"jpegbytes"))
    assert result["screen_title"] == "Advanced"
    assert len(poster.bodies) == 2
    assert poster.bodies[1].get("response_format", {}).get("type") != "json_schema"


def test_openrouter_default_model_is_free():
    client = VLMClient(provider="openrouter", api_key="k")
    assert client._resolved_model().endswith(":free")


def test_vlm_api_key_resolves_from_doppler(monkeypatch):
    from src.kvm_core import doppler_credentials as dc

    monkeypatch.delenv("VLM_API_KEY", raising=False)
    dc._clear_vlm_key_cache()
    calls = {"n": 0}

    def fake_resolve(*, require=True):
        calls["n"] += 1
        return "sk-or-doppler"

    monkeypatch.setattr(dc, "resolve_vlm_api_key", fake_resolve)
    client = VLMClient(provider="openrouter", model="m")
    client._validate_configuration()
    assert client.api_key == "sk-or-doppler"
    assert calls["n"] == 1


def test_vlm_key_doppler_cache_and_clear(monkeypatch):
    from src.kvm_core import doppler_credentials as dc

    dc._clear_vlm_key_cache()
    reads = {"n": 0}

    def fake_reader(name, project, config):
        reads["n"] += 1
        return "sk-or-cached" if name == "OPENROUTER_API_KEY" else None

    monkeypatch.setattr(dc, "_doppler_get_plain", fake_reader)
    monkeypatch.setattr(dc, "assert_doppler_authenticated", lambda *a, **k: None)
    assert dc.resolve_vlm_api_key(require=True) == "sk-or-cached"
    first = reads["n"]
    assert dc.resolve_vlm_api_key(require=True) == "sk-or-cached"
    assert reads["n"] == first  # cached — no second CLI probe
    dc._clear_vlm_key_cache()


# --- Mock provider ---------------------------------------------------------


def test_mock_provider_emits_v2():
    client = VLMClient(provider="mock")
    result = _run(client.parse_screenshot(b"any-image-bytes"))
    parsed = BiosScreenParse.model_validate(result)
    assert parsed.screen_kind is not None
    assert parsed.layout is not None
    assert parsed.hotkeys, "mock must exercise the hotkeys field"
    assert parsed.confidence is not None
    assert any(e.selected for e in parsed.entries)
