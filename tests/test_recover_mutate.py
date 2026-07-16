"""Executable safety-rig tests for recovery and BIOS mutation paths."""
from __future__ import annotations

import asyncio

from src.bios_sidecar.controller.mutate import BiosMutator
from src.bios_sidecar.controller.recover import BiosRecoveryHandler
from src.bios_sidecar.domain.enums import ControlRole, RiskClass, StateKind
from src.bios_sidecar.domain.models import ControlEntry
from src.bios_sidecar.state.capability_index import CapabilityIndex
from src.bios_sidecar.state.store import SQLiteStore
from tests.bios_test_helpers import (
    NoWaitSettler,
    ScriptedCometClient,
    ScriptedObserver,
    make_bios_state,
)


def run(coro):
    return asyncio.run(coro)


class TestRecover:
    def test_abort_releases_keys_and_sends_three_escapes(self):
        settler = NoWaitSettler()
        handler = BiosRecoveryHandler(settler=settler)
        client = ScriptedCometClient()

        result = run(handler.abort_and_recover(client))

        assert result == "recovery_completed"
        assert client.release_calls == 1
        assert client.sent_combos == ["Escape", "Escape", "Escape"]
        assert settler.fixed_waits == [0.1, 0.25, 0.25, 0.25]


class TestMutateSaveDialog:
    @staticmethod
    def mutator(states) -> BiosMutator:
        return BiosMutator(
            observer=ScriptedObserver(states),
            settler=NoWaitSettler(),
        )

    def test_save_dialog_keyword_pass_confirms_enter(self):
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
        mutator = self.mutator([pre, dialog, post])
        client = ScriptedCometClient()

        ok, final, msg = run(
            mutator.save_and_reboot(client, "run", "dev", reboot_observe_seconds=2.0)
        )

        assert ok is True
        assert "confirmed" in msg.lower()
        assert "reboot observed" in msg.lower()
        assert final is post
        assert client.sent_combos == ["F10", "Enter"]

    def test_save_dialog_modal_present_pass_confirms_enter(self):
        pre = make_bios_state(screen_title="SETTINGS", modal_present=False)
        dialog = make_bios_state(
            state_id="state_modal",
            screen_title="Untitled Dialog",
            screen_kind=StateKind.CONFIRMATION_MODAL,
            modal_present=True,
            modal_type="confirm",
        )
        post = make_bios_state(
            state_id="state_nosignal",
            screen_title="",
            screen_kind=StateKind.NO_SIGNAL,
        )
        mutator = self.mutator([pre, dialog, post])
        client = ScriptedCometClient()

        ok, final, msg = run(
            mutator.save_and_reboot(client, "run", "dev", reboot_observe_seconds=2.0)
        )

        assert ok is True
        assert client.sent_combos == ["F10", "Enter"]
        assert final is post
        assert "reboot_observed" in msg

    def test_unrelated_modal_fail_closed_without_save_keywords(self):
        pre = make_bios_state(screen_title="SETTINGS", modal_present=False)
        dialog = make_bios_state(
            state_id="state_modal",
            screen_title="Network Notice",
            modal_present=True,
            modal_type="info",
        )
        mutator = self.mutator([pre, dialog])
        client = ScriptedCometClient()

        ok, final, msg = run(mutator.save_and_reboot(client, "run", "dev"))

        assert ok is False
        assert "abort" in msg.lower() or "not detected" in msg.lower()
        assert client.sent_combos == ["F10"]
        assert final is dialog

    def test_save_dialog_fail_closed_without_keyword_or_modal(self):
        plain = make_bios_state(screen_title="Advanced SETTINGS", modal_present=False)
        mutator = self.mutator([plain])
        client = ScriptedCometClient()

        ok, final, msg = run(mutator.save_and_reboot(client, "run", "dev"))

        assert ok is False
        assert "abort" in msg.lower() or "not detected" in msg.lower()
        assert client.sent_combos == ["F10"]
        assert final is plain


class TestMutateApply:
    @staticmethod
    def seeded_store() -> SQLiteStore:
        store = SQLiteStore(db_path=":memory:")
        CapabilityIndex(store)
        return store

    def test_apply_setting_change_verifies_new_value(self):
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
        store = self.seeded_store()
        observer = ScriptedObserver([before, after], store=store)
        mutator = BiosMutator(observer=observer, settler=NoWaitSettler())
        client = ScriptedCometClient()
        try:
            ok, final, msg = run(
                mutator.apply_setting_change(
                    client, "run", "dev", "cpu_cooler_tuning", "Box Cooler"
                )
            )
        finally:
            store.close()

        assert ok is True
        assert "successfully" in msg.lower() or "confirmed" in msg.lower()
        assert final is after
        assert "Enter" in client.sent_combos
        assert client.sent_combos.count("ArrowUp") == 2

    def test_apply_rejects_when_cursor_misaligned(self):
        store = self.seeded_store()
        observer = ScriptedObserver(
            [
                make_bios_state(
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
            ],
            store=store,
        )
        mutator = BiosMutator(observer=observer, settler=NoWaitSettler())
        client = ScriptedCometClient()
        try:
            ok, _final, msg = run(
                mutator.apply_setting_change(
                    client, "run", "dev", "cpu_cooler_tuning", "Tower Cooler"
                )
            )
        finally:
            store.close()

        assert ok is False
        assert "Alignment mismatch" in msg
        assert client.sent_combos == []
