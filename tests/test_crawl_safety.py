import unittest

from src.bios_sidecar.controller.crawl import BiosCrawler
from src.bios_sidecar.domain.enums import ControlRole, RiskClass, StateKind
from src.bios_sidecar.domain.models import (
    ActionPolicies,
    BiosMetadata,
    BiosState,
    ConfidenceMetrics,
    ControlEntry,
    FrameMetadata,
    LocationMetadata,
    RiskStatus,
    SelectionMetadata,
)


def _state(*, blocklisted: bool, actions: ActionPolicies) -> BiosState:
    return BiosState(
        state_id="state",
        run_id="run",
        device_id="device",
        frame=FrameMetadata("shot", "sha", "phash", [1920, 1080], "2026-07-10T00:00:00"),
        bios=BiosMetadata("MSI", "Z690", "Click BIOS", "advanced"),
        location=LocationMetadata(StateKind.FLASH_UTILITY if blocklisted else StateKind.MENU_LIST, "SETTINGS", []),
        selection=SelectionMetadata(0, "Firmware Update", None),
        controls=[
            ControlEntry(
                "firmware_update",
                "Firmware Update",
                None,
                ControlRole.SUBMENU,
                True,
                RiskClass.BLOCKED if blocklisted else RiskClass.LOW,
            )
        ],
        risk=RiskStatus(blocklist_flag=blocklisted),
        actions=actions,
        confidence=ConfidenceMetrics(1.0, 1.0, 1.0),
    )


class CrawlSafetyTest(unittest.TestCase):
    def test_blocklisted_state_never_offers_or_selects_enter(self):
        crawler = BiosCrawler(observer=None, settler=None)
        state = _state(blocklisted=True, actions=ActionPolicies(safe=["Escape"]))

        crawler._enumerate_frontier(state, "state")

        self.assertEqual([], crawler._frontier)
        self.assertEqual("Escape", crawler._heuristic_pick(state))

    def test_normalized_safe_actions_allow_expected_navigation(self):
        crawler = BiosCrawler(observer=None, settler=None)
        state = _state(
            blocklisted=False,
            actions=ActionPolicies(safe=["ArrowDown", "Escape"], context_gated=["Enter"]),
        )

        crawler._enumerate_frontier(state, "state")

        self.assertEqual(["Enter", "ArrowDown"], [edge.action_key for edge in crawler._frontier])
        self.assertEqual("Enter", crawler._heuristic_pick(state))

    def test_selected_blocked_control_never_entered_even_when_enter_allowed(self):
        # Even if a stale/foreign state offers Enter, a control whose own risk
        # is BLOCKED (e.g. the M-FLASH tile) must never be a crawl candidate.
        crawler = BiosCrawler(observer=None, settler=None)
        state = _state(
            blocklisted=False,
            actions=ActionPolicies(safe=["ArrowDown", "Escape"], context_gated=["Enter"]),
        )
        state.controls[0].risk = RiskClass.BLOCKED

        crawler._enumerate_frontier(state, "state")

        self.assertEqual(["ArrowDown"], [edge.action_key for edge in crawler._frontier])
        self.assertEqual("ArrowDown", crawler._heuristic_pick(state))

    def test_heuristic_never_escapes_root_screen(self):
        # Escape on the home dashboard raises "Quit without saving?" — the
        # heuristic must stop instead of falling back to it there.
        crawler = BiosCrawler(observer=None, settler=None)
        state = _state(
            blocklisted=False,
            actions=ActionPolicies(safe=["Escape"], context_gated=[]),
        )
        state.location.screen_kind = StateKind.EZ_MODE
        state.controls = []

        self.assertIsNone(crawler._heuristic_pick(state))
