import unittest
from src.bios_sidecar.domain.models import BiosState, FrameMetadata, BiosMetadata, LocationMetadata, SelectionMetadata, ControlEntry, ModalMetadata, RiskStatus, ActionPolicies, ConfidenceMetrics, TraceEvent
from src.bios_sidecar.domain.enums import StateKind, ControlRole, RiskClass, PolicyProfile, EventClass
from src.bios_sidecar.policy.engine import PolicyEngine
from src.bios_sidecar.policy.approvals import ApprovalTracker
from src.bios_sidecar.state.store import SQLiteStore

class TestPolicyEngine(unittest.TestCase):
    def setUp(self):
        self.store = SQLiteStore(db_path=":memory:")
        self.tracker = ApprovalTracker(self.store)
        self.engine = PolicyEngine(approval_tracker=self.tracker)

        # Construct standard safe state block
        self.safe_state = BiosState(
            state_id="state_safe",
            run_id="run_123",
            device_id="comet_123",
            frame=FrameMetadata("shot_1", "sha_1", "hash_1", [1024, 768], "now"),
            bios=BiosMetadata("msi", "z690", "click_bios", "advanced"),
            location=LocationMetadata(StateKind.SETTING_LIST, "OC", ["OC", "CPU Features"], "CPU Features"),
            selection=SelectionMetadata(0, "CPU Lite Load", "Mode 9"),
            controls=[
                ControlEntry("ctrl_0", "CPU Lite Load", "Mode 9", ControlRole.SETTING, True, RiskClass.MEDIUM),
                ControlEntry("ctrl_1", "Advanced CPU Configuration", None, ControlRole.SUBMENU, False, RiskClass.LOW)
            ],
            modal=ModalMetadata(False),
            risk=RiskStatus(False),
            actions=ActionPolicies(),
            confidence=ConfidenceMetrics(1.0, 1.0, 1.0)
        )

        # Construct hazardous screen containing password
        self.hazard_state = BiosState(
            state_id="state_hazard",
            run_id="run_123",
            device_id="comet_123",
            frame=FrameMetadata("shot_2", "sha_2", "hash_2", [1024, 768], "now"),
            bios=BiosMetadata("msi", "z690", "click_bios", "advanced"),
            location=LocationMetadata(StateKind.PASSWORD_PROMPT, "SECURITY", ["SECURITY", "Set Password"], "Set Password"),
            selection=SelectionMetadata(0, "Set Password", None),
            controls=[
                ControlEntry("ctrl_0", "Set Administrator Password", None, ControlRole.SETTING, True, RiskClass.BLOCKED)
            ],
            modal=ModalMetadata(False),
            risk=RiskStatus(True, ["Password"]),
            actions=ActionPolicies(),
            confidence=ConfidenceMetrics(1.0, 1.0, 1.0)
        )

    def test_navigation_is_allowed(self):
        decision = self.engine.evaluate(self.safe_state, "ArrowDown", PolicyProfile.READ_ONLY_CRAWL)
        self.assertEqual(decision.decision, "allowed")
        self.assertEqual(decision.reason, "NAVIGATION_PERMITTED")

    def test_arrow_down_is_blocked_in_observe_only(self):
        decision = self.engine.evaluate(self.safe_state, "ArrowDown", PolicyProfile.OBSERVE_ONLY)
        self.assertEqual(decision.decision, "blocked")
        self.assertEqual(decision.reason, "OBSERVE_ONLY_PROFILE")

    def test_enter_on_submenu_is_allowed_in_crawl(self):
        # Set selection row to submenu "Advanced CPU Configuration"
        self.safe_state.controls[0].selected = False
        self.safe_state.controls[1].selected = True

        decision = self.engine.evaluate(self.safe_state, "Enter", PolicyProfile.READ_ONLY_CRAWL)
        self.assertEqual(decision.decision, "allowed")
        self.assertEqual(decision.reason, "ENTER_SUBMENU_SAFE")

    def test_enter_on_setting_is_blocked_in_crawl(self):
        # Default selected is row 0 "CPU Lite Load" (SETTING)
        decision = self.engine.evaluate(self.safe_state, "Enter", PolicyProfile.READ_ONLY_CRAWL)
        self.assertEqual(decision.decision, "blocked")
        self.assertEqual(decision.reason, "ENTER_SETTING_BLOCKED_IN_CRAWL")

    def test_enter_on_setting_requires_approval_in_mutation(self):
        decision = self.engine.evaluate(self.safe_state, "Enter", PolicyProfile.SUPERVISED_MUTATION)
        self.assertEqual(decision.decision, "requires_approval")
        self.assertTrue(decision.required_approval)

    def test_enter_on_setting_allowed_with_approval_in_mutation(self):
        app_id = self.tracker.request_approval("plan_1")
        self.tracker.grant_approval(app_id, "test_operator")

        decision = self.engine.evaluate(self.safe_state, "Enter", PolicyProfile.SUPERVISED_MUTATION, approval_id=app_id)
        self.assertEqual(decision.decision, "allowed")
        self.assertEqual(decision.reason, "MUTATION_AUTHORIZED_BY_HUMAN_FOR:CPU Lite Load")

    def test_f10_save_blocked_without_approval(self):
        decision = self.engine.evaluate(self.safe_state, "F10", PolicyProfile.SUPERVISED_MUTATION)
        self.assertEqual(decision.decision, "requires_approval")

    def test_f10_save_allowed_with_approval(self):
        app_id = self.tracker.request_approval("plan_1")
        self.tracker.grant_approval(app_id, "test_operator")

        decision = self.engine.evaluate(self.safe_state, "F10", PolicyProfile.SUPERVISED_MUTATION, approval_id=app_id)
        self.assertEqual(decision.decision, "allowed")
        self.assertEqual(decision.reason, "F10_SAVE_AUTHORIZED_BY_HUMAN")

    def test_hazards_blocked(self):
        decision = self.engine.evaluate(self.hazard_state, "Enter", PolicyProfile.READ_ONLY_CRAWL)
        self.assertEqual(decision.decision, "blocked")
        self.assertTrue("HAZARDS_DETECTED" in decision.reason)

    def test_bios_state_default_actions_serializes(self):
        state = BiosState(
            state_id="state_default_actions",
            run_id="run_123",
            device_id="comet_123",
            frame=FrameMetadata("shot_1", "sha_1", "hash_1", [1024, 768], "now"),
            bios=BiosMetadata("msi", "z690", "click_bios", "advanced"),
            location=LocationMetadata(StateKind.SETTING_LIST, "OC", ["OC"], "OC"),
            selection=SelectionMetadata(0, "CPU Lite Load", "Mode 9"),
        )

        self.assertIn("actions", state.to_dict())

    def test_trace_event_round_trip_serializes(self):
        event = TraceEvent(
            event_id="evt_1",
            run_id="run_123",
            timestamp="now",
            event_type=EventClass.ACTION_EXECUTED,
            requested_action={"key": "Enter"},
        )

        self.store.save_trace_event(event)
        loaded = self.store.list_trace_events("run_123")[0]
        self.assertEqual(loaded.event_type, EventClass.ACTION_EXECUTED)
        self.assertEqual(loaded.to_dict()["event_type"], "ACTION_EXECUTED")

if __name__ == "__main__":
    unittest.main()
