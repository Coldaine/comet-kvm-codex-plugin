"""Unit tests for recover.py and mutate.py save-dialog / mutation paths."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from src.bios_sidecar.controller.mutate import BiosMutator
from src.bios_sidecar.controller.recover import BiosRecoveryHandler
from src.bios_sidecar.controller.settle import ScreenSettler
from src.bios_sidecar.domain.enums import ControlRole, RiskClass, StateKind
from src.bios_sidecar.domain.models import ControlEntry
from tests.bios_test_helpers import FakeCometClient, make_bios_state


def _run(coro):
    return asyncio.run(coro)


class TestRecover:
    def test_abort_releases_keys_and_sends_three_escapes(self):
        settler = ScreenSettler()
        settler.wait_fixed = AsyncMock()
        handler = BiosRecoveryHandler(settler=settler)
        client = FakeCometClient()

        result = _run(handler.abort_and_recover(client))

        assert result == "recovery_completed"
        assert client.release_calls == 1
        assert client.sent_combos == ["Escape", "Escape", "Escape"]
        assert settler.wait_fixed.await_count >= 4  # release pause + 3 Esc pauses


class TestMutateSaveDialog:
    def _mutator(self) -> BiosMutator:
        observer = MagicMock()
        settler = ScreenSettler()
        settler.wait_for_settle = AsyncMock(return_value=b"")
        return BiosMutator(observer=observer, settler=settler)

    def test_save_dialog_keyword_pass_confirms_enter(self):
        mutator = self._mutator()
        client = FakeCometClient()
        pre = make_bios_state(screen_title="Advanced SETTINGS", modal_present=False)
        dialog = make_bios_state(
            state_id="state_save",
            screen_title="Save & Exit Setup",
            screen_kind=StateKind.SAVE_CHANGES_MODAL,
            modal_present=False,
        )
        post = make_bios_state(
            state_id="state_post",
            screen_title="POST",
            screen_kind=StateKind.POST_SCREEN,
        )
        mutator.observer.observe_state = AsyncMock(side_effect=[pre, dialog, post])

        ok, final, msg = _run(
            mutator.save_and_reboot(client, "run", "dev", reboot_observe_seconds=2.0)
        )

        assert ok is True
        assert "confirmed" in msg.lower()
        assert "reboot observed" in msg.lower()
        assert final is post
        assert client.sent_combos == ["F10", "Enter"]

    def test_save_dialog_modal_present_pass_confirms_enter(self):
        mutator = self._mutator()
        client = FakeCometClient()
        pre = make_bios_state(screen_title="SETTINGS", modal_present=False)
        dialog = make_bios_state(
            state_id="state_modal",
            screen_title="Untitled Dialog",
            modal_present=True,
            modal_type="confirm",
        )
        post = make_bios_state(
            state_id="state_nosignal",
            screen_title="",
            screen_kind=StateKind.NO_SIGNAL,
        )
        mutator.observer.observe_state = AsyncMock(side_effect=[pre, dialog, post])

        ok, final, msg = _run(
            mutator.save_and_reboot(client, "run", "dev", reboot_observe_seconds=2.0)
        )

        assert ok is True
        assert client.sent_combos == ["F10", "Enter"]
        assert final is post
        assert "reboot_observed" in msg

    def test_unrelated_modal_fail_closed_without_save_keywords(self):
        mutator = self._mutator()
        client = FakeCometClient()
        pre = make_bios_state(screen_title="SETTINGS", modal_present=False)
        dialog = make_bios_state(
            state_id="state_modal",
            screen_title="Network Notice",
            modal_present=True,
            modal_type="info",
        )
        mutator.observer.observe_state = AsyncMock(side_effect=[pre, dialog])

        ok, final, msg = _run(mutator.save_and_reboot(client, "run", "dev"))

        assert ok is False
        assert "abort" in msg.lower() or "not detected" in msg.lower()
        assert client.sent_combos == ["F10"]
        assert "Enter" not in client.sent_combos
        assert final is dialog

    def test_save_dialog_fail_closed_without_keyword_or_modal(self):
        mutator = self._mutator()
        client = FakeCometClient()
        plain = make_bios_state(screen_title="Advanced SETTINGS", modal_present=False)
        mutator.observer.observe_state = AsyncMock(return_value=plain)

        ok, final, msg = _run(mutator.save_and_reboot(client, "run", "dev"))

        assert ok is False
        assert "abort" in msg.lower() or "not detected" in msg.lower()
        assert client.sent_combos == ["F10"]
        assert "Enter" not in client.sent_combos
        assert final is plain


class TestMutateApply:
    def test_apply_setting_change_verifies_new_value(self):
        observer = MagicMock()
        # Capability priors live on a real CapabilityIndex via observer.store —
        # stub resolve path by patching CapabilityIndex used inside mutator.
        settler = ScreenSettler()
        settler.wait_for_settle = AsyncMock(return_value=b"")
        mutator = BiosMutator(observer=observer, settler=settler)
        client = FakeCometClient()

        before = make_bios_state(
            state_id="before",
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
            state_id="after",
            screen_title="EZ Mode",
            controls=[
                ControlEntry(
                    "ctrl_000",
                    "CPU Cooler Tuning",
                    "Box Cooler",
                    ControlRole.SETTING,
                    True,
                    RiskClass.MEDIUM,
                    options=["Box Cooler", "Tower Cooler", "Water Cooler"],
                )
            ],
        )
        observer.observe_state = AsyncMock(side_effect=[before, after])
        observer.store = MagicMock()

        from src.bios_sidecar.state.capability_index import CapabilityIndex
        from src.bios_sidecar.state.store import SQLiteStore

        store = SQLiteStore(db_path=":memory:")
        CapabilityIndex(store)  # seed MSI priors into store
        observer.store = store

        ok, final, msg = _run(
            mutator.apply_setting_change(
                client, "run", "dev", "cpu_cooler_tuning", "Box Cooler"
            )
        )
        store.close()

        assert ok is True
        assert "successfully" in msg.lower() or "confirmed" in msg.lower()
        assert final is after
        assert "Enter" in client.sent_combos
        assert client.sent_combos.count("ArrowUp") == 2  # index 2 → 0

    def test_apply_rejects_when_cursor_misaligned(self):
        observer = MagicMock()
        settler = ScreenSettler()
        settler.wait_for_settle = AsyncMock(return_value=b"")
        mutator = BiosMutator(observer=observer, settler=settler)
        client = FakeCometClient()

        from src.bios_sidecar.state.store import SQLiteStore
        from src.bios_sidecar.state.capability_index import CapabilityIndex

        store = SQLiteStore(db_path=":memory:")
        CapabilityIndex(store)  # seed priors
        observer.store = store
        observer.observe_state = AsyncMock(
            return_value=make_bios_state(
                controls=[
                    ControlEntry(
                        "ctrl_000",
                        "Unrelated Setting",
                        "On",
                        ControlRole.SETTING,
                        True,
                        RiskClass.LOW,
                        options=["On", "Off"],
                    )
                ]
            )
        )

        ok, _final, msg = _run(
            mutator.apply_setting_change(
                client, "run", "dev", "cpu_cooler_tuning", "Tower Cooler"
            )
        )
        store.close()

        assert ok is False
        assert "Alignment mismatch" in msg
        assert client.sent_combos == []
