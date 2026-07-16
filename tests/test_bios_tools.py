"""Behavioral tests for bios_* MCP tools, mock-VLM guard, and OCR-first observe."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from src.bios_sidecar.domain.enums import ControlRole, RiskClass, RuntimeState
from src.bios_sidecar.domain.models import ControlEntry
from src.bios_sidecar.mcp import server as bios_server
from tests.bios_test_helpers import (
    build_runtime,
    cleanup_runtime,
    jpeg_bytes,
    make_bios_state,
    patch_ocr_texts,
)


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# 4a — bios_* MCP tool behavior
# ---------------------------------------------------------------------------


class TestBiosTools:
    def test_bios_observe_state_returns_bios_state_dict(self, tmp_path):
        runtime, _client = build_runtime(tmp_path)
        try:
            with patch.object(bios_server, "get_runtime", return_value=runtime):
                result = _run(bios_server.bios_observe_state())

            assert isinstance(result, dict)
            assert "state_id" in result
            assert "location" in result
            assert "frame" in result
            assert "controls" in result
            assert result["frame"]["screenshot_id"]
            assert runtime.state == RuntimeState.SYNCED
        finally:
            cleanup_runtime(runtime)

    def test_bios_crawl_step_returns_state_edge_recommendation(self, tmp_path):
        runtime, client = build_runtime(tmp_path)
        try:
            with patch.object(bios_server, "get_runtime", return_value=runtime):
                _run(bios_server.bios_observe_state())
                # Distinct frame after crawl key so observe can produce a new node/edge.
                client.screenshot = jpeg_bytes(color=(90, 20, 30))
                result = _run(bios_server.bios_crawl_step())

            assert "state" in result
            assert "created_edge" in result
            assert "recommendation" in result
            assert isinstance(result["state"], dict)
            assert "state_id" in result["state"]
            assert result["recommendation"] in ("continue", "backtrack", "stop", "complete")
            assert client.sent_combos  # at least one crawl key
        finally:
            cleanup_runtime(runtime)

    def test_bios_navigate_to_known_vs_unknown(self, tmp_path):
        runtime, _client = build_runtime(tmp_path)
        try:
            with patch.object(bios_server, "get_runtime", return_value=runtime):
                _run(bios_server.bios_observe_state())
                known_id = runtime.syncer.current_matched_node.node_id
                assert known_id

                known = _run(bios_server.bios_navigate_to(known_id))
                unknown = _run(bios_server.bios_navigate_to("node_does_not_exist"))

            assert known["success"] is True
            assert "Already at target" in known["message"] or known["final_state"] is not None

            assert unknown["success"] is False
            assert "No path found" in unknown["message"]
        finally:
            cleanup_runtime(runtime)

    def test_bios_apply_setting_change(self, tmp_path):
        runtime, client = build_runtime(tmp_path)
        try:
            # Seed SYNCED via observe, then drive mutator with controlled observes.
            with patch.object(bios_server, "get_runtime", return_value=runtime):
                _run(bios_server.bios_observe_state())

            before = make_bios_state(
                state_id="state_before",
                screen_title="EZ Mode",
                controls=[
                    ControlEntry(
                        "ctrl_000",
                        "CPU Cooler Tuning",
                        "Water Cooler",
                        ControlRole.SETTING,
                        True,
                        RiskClass.MEDIUM,
                        options=["Box Cooler", "Tower Cooler", "Water Cooler"],
                    )
                ],
            )
            after = make_bios_state(
                state_id="state_after",
                screen_title="EZ Mode",
                controls=[
                    ControlEntry(
                        "ctrl_000",
                        "CPU Cooler Tuning",
                        "Tower Cooler",
                        ControlRole.SETTING,
                        True,
                        RiskClass.MEDIUM,
                        options=["Box Cooler", "Tower Cooler", "Water Cooler"],
                    )
                ],
            )
            observe = AsyncMock(side_effect=[before, after])
            runtime.mutator.observer.observe_state = observe

            with patch.object(bios_server, "get_runtime", return_value=runtime):
                result = _run(
                    bios_server.bios_apply_setting_change("cpu_cooler_tuning", "Tower Cooler")
                )

            assert result["success"] is True
            assert "confirmed" in result["message"].lower() or "successfully" in result["message"].lower()
            assert result["state"] is not None
            assert "Enter" in client.sent_combos
            assert "ArrowUp" in client.sent_combos  # Water(2) → Tower(1)
        finally:
            cleanup_runtime(runtime)

    def test_bios_save_and_reboot_aborts_without_save_dialog(self, tmp_path):
        runtime, client = build_runtime(tmp_path)
        try:
            with patch.object(bios_server, "get_runtime", return_value=runtime):
                _run(bios_server.bios_observe_state())

            plain = make_bios_state(screen_title="Advanced SETTINGS", modal_present=False)
            runtime.mutator.observer.observe_state = AsyncMock(return_value=plain)

            with patch.object(bios_server, "get_runtime", return_value=runtime):
                result = _run(bios_server.bios_save_and_reboot())

            assert result["success"] is False
            assert "abort" in result["message"].lower() or "not detected" in result["message"].lower()
            assert "F10" in client.sent_combos
            assert "Enter" not in client.sent_combos  # fail-closed: no confirm
        finally:
            cleanup_runtime(runtime)

    def test_bios_abort_and_recover(self, tmp_path):
        runtime, client = build_runtime(tmp_path)
        try:
            with patch.object(bios_server, "get_runtime", return_value=runtime):
                # attach path needs a connected client; recover then re-observes
                result = _run(bios_server.bios_abort_and_recover())

            assert result["status"] == "recovery_completed"
            assert client.release_calls == 1
            assert client.sent_combos.count("Escape") == 3
            assert runtime.state in (RuntimeState.SYNCED, RuntimeState.DEGRADED)
        finally:
            cleanup_runtime(runtime)


# ---------------------------------------------------------------------------
# 4c — Mock VLM hard-fail on live-looking Comet
# ---------------------------------------------------------------------------


class TestMockVlmGuard:
    def test_observe_raises_when_mock_vlm_and_live_client(self, tmp_path):
        # Non-fixture host ⇒ treated as live; mock provider must hard-fail.
        runtime, _client = build_runtime(tmp_path, host="10.20.30.40")
        try:
            with pytest.raises(RuntimeError, match="VLM_PROVIDER=mock"):
                _run(runtime.observe_state())
        finally:
            cleanup_runtime(runtime)

    def test_bios_observe_state_raises_via_mcp_on_live_mock(self, tmp_path):
        runtime, _client = build_runtime(tmp_path, host="172.16.5.9")
        try:
            with patch.object(bios_server, "get_runtime", return_value=runtime):
                with pytest.raises(RuntimeError, match="live Comet"):
                    _run(bios_server.bios_observe_state())
        finally:
            cleanup_runtime(runtime)

    def test_fixture_host_allows_mock_vlm(self, tmp_path):
        runtime, _client = build_runtime(tmp_path, host="127.0.0.1")
        try:
            state = _run(runtime.observe_state())
            assert state.state_id
            assert runtime.state == RuntimeState.SYNCED
        finally:
            cleanup_runtime(runtime)


# ---------------------------------------------------------------------------
# 4d — Page identity reuse still re-extracts live interaction via VLM
# ---------------------------------------------------------------------------


class TestLiveInteractionObserve:
    def test_matched_screen_still_calls_vlm_for_live_fields(self, tmp_path):
        shot = jpeg_bytes(color=(12, 34, 56))
        runtime, client = build_runtime(tmp_path, screenshot=shot)
        patch_ocr_texts(runtime, ["EZ", "Mode", "Cooler"])
        try:
            first = _run(runtime.observer.observe_state(client, "run_a", "dev_a"))
            assert first.state_id

            with patch.object(
                runtime.vlm_client,
                "parse_screenshot",
                new_callable=AsyncMock,
                return_value={
                    "screen_title": "EZ Mode",
                    "menu_path": ["EZ Mode"],
                    "cursor_at": 0,
                    "entries": [
                        {
                            "label": "Cooler",
                            "type": "leaf-enum",
                            "value": "Auto",
                            "options": ["Auto", "Enabled"],
                            "key_to_enter": "Enter",
                        }
                    ],
                    "blocklist_flag": False,
                    "blocklist_keywords": [],
                },
            ) as spy:
                second = _run(runtime.observer.observe_state(client, "run_a", "dev_a"))
                spy.assert_called_once()

            assert second.state_id != first.state_id
            assert second.selection.label == "Cooler"
            assert second.frame.perceptual_hash == first.frame.perceptual_hash
        finally:
            cleanup_runtime(runtime)
