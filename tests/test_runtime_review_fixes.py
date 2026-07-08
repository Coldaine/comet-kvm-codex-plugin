import tempfile
import unittest

import glkvm_mcp
from glkvm_mcp import _safe_screenshot_path, get_runtime
from src.bios_sidecar.comet.capture import CaptureManager
from src.bios_sidecar.controller.crawl import BiosCrawler
from src.bios_sidecar.controller.mutate import BiosMutator
from src.bios_sidecar.controller.runtime import StatefulBiosRuntime
from src.bios_sidecar.domain.enums import ControlRole, RiskClass, RuntimeState, StateKind
from src.bios_sidecar.domain.models import (
    ActionPolicies,
    BiosMetadata,
    BiosState,
    ConfidenceMetrics,
    ControlEntry,
    FrameMetadata,
    LocationMetadata,
    ModalMetadata,
    RiskStatus,
    SelectionMetadata,
)
from src.bios_sidecar.perception.normalize import normalize_bios_state
from src.bios_sidecar.policy.approvals import ApprovalTracker
from src.bios_sidecar.policy.engine import PolicyEngine
from src.bios_sidecar.state.capability_index import CapabilityIndex
from src.bios_sidecar.state.store import SQLiteStore


class FakeClient:
    def __init__(self):
        self.sent = []

    async def get_screenshot(self, preview=False, max_width=1920, quality=80):
        return b"same frame bytes"

    def is_connected(self):
        return True

    async def send_combo(self, combo):
        self.sent.append(combo)


class FakeSettler:
    async def wait_for_settle(self, client):
        return {"stable": True}


class FakeObserver:
    def __init__(self, store, state):
        self.store = store
        self.state = state

    async def observe_state(self, client, run_id, device_id, previous_state=None, last_action=None):
        return self.state


class FakeCrawler:
    def __init__(self, state):
        self.state = state

    async def execute_crawl_step(self, client, run_id, device_id, current_state, policy_profile):
        return self.state, None, "continue"


def _state(options=None, value="Mode 9", state_id="state_safe"):
    return BiosState(
        state_id=state_id,
        run_id="run_123",
        device_id="comet_123",
        frame=FrameMetadata("shot_1", "sha_1", "hash_1", [1024, 768], "now"),
        bios=BiosMetadata("msi", "z690", "click_bios", "advanced"),
        location=LocationMetadata(StateKind.SETTING_LIST, "OC", ["OC", "CPU Features"], "CPU Features"),
        selection=SelectionMetadata(0, "CPU Lite Load", value),
        controls=[
            ControlEntry("ctrl_0", "CPU Lite Load", value, ControlRole.SETTING, True, RiskClass.MEDIUM, options=options),
        ],
        modal=ModalMetadata(False),
        risk=RiskStatus(False),
        actions=ActionPolicies(),
        confidence=ConfidenceMetrics(1.0, 1.0, 1.0),
    )


class RuntimeReviewFixesTest(unittest.IsolatedAsyncioTestCase):
    async def test_runtime_observe_requires_connection(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = StatefulBiosRuntime(db_path=f"{tmp}/state.db", screenshot_cache=f"{tmp}/screens")
            try:
                with self.assertRaisesRegex(RuntimeError, "Not connected"):
                    await runtime.observe_state()
            finally:
                runtime.vlm_client.close()
                runtime.store.close()

    async def test_capture_ids_do_not_collide_for_identical_frames(self):
        with tempfile.TemporaryDirectory() as tmp:
            capture = CaptureManager(cache_dir=tmp)
            _, shot1, path1 = await capture.capture_frame(FakeClient())
            _, shot2, path2 = await capture.capture_frame(FakeClient())
            self.assertNotEqual(shot1, shot2)
            self.assertNotEqual(path1, path2)

    async def test_mutation_refuses_non_deterministic_value_selection(self):
        store = SQLiteStore(db_path=":memory:")
        try:
            CapabilityIndex(store)
            approval_tracker = ApprovalTracker(store)
            approval_id = approval_tracker.request_approval("plan_1")
            approval_tracker.grant_approval(approval_id, "tester")
            client = FakeClient()
            mutator = BiosMutator(
                observer=FakeObserver(store, _state(options=None)),
                policy_engine=PolicyEngine(approval_tracker),
                settler=FakeSettler(),
            )

            ok, _, message = await mutator.apply_setting_change(
                client, "run_123", "device_123", "plan_1", approval_id, "cpu_lite_load_mode", "Mode 8"
            )

            self.assertFalse(ok)
            self.assertIn("deterministically", message)
            self.assertEqual(client.sent, [])
        finally:
            store.close()

    async def test_crawl_step_logs_original_state_before(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = StatefulBiosRuntime(db_path=f"{tmp}/state.db", screenshot_cache=f"{tmp}/screens")
            try:
                runtime.client = FakeClient()
                runtime.state = RuntimeState.SYNCED
                runtime.run_id = "run_123"
                runtime.device_id = "device_123"
                runtime.current_state_rec = _state(state_id="state_before")
                runtime.crawler = FakeCrawler(_state(value="Mode 8", state_id="state_after"))

                state, _, _ = await runtime.crawl_step()

                event = runtime.store.list_trace_events("run_123")[-1]
                self.assertEqual(state.state_id, "state_after")
                self.assertEqual(event.state_before, "state_before")
                self.assertEqual(event.state_after, "state_after")
            finally:
                runtime.vlm_client.close()
                runtime.store.close()

    async def test_crawler_registers_discovered_setting_capability(self):
        store = SQLiteStore(db_path=":memory:")
        try:
            observer = FakeObserver(store, _state())
            crawler = BiosCrawler(observer=observer, policy_engine=None, settler=FakeSettler())
            crawler._register_setting_capabilities(_state(), "node_1")

            cap = CapabilityIndex(store).resolve_capability_by_handle("cpu_lite_load_mode")
            self.assertIsNotNone(cap)
            self.assertTrue(any(path.node_id == "node_1" for path in cap.paths))
        finally:
            store.close()


class RuntimeHelperReviewFixesTest(unittest.TestCase):
    def tearDown(self):
        runtime = get_runtime()
        try:
            runtime.vlm_client.close()
            runtime.store.close()
        finally:
            glkvm_mcp._runtime = None

    def test_safe_screenshot_path_rejects_absolute_and_parent_traversal(self):
        with self.assertRaises(ValueError):
            _safe_screenshot_path("../outside.jpg")
        with self.assertRaises(ValueError):
            _safe_screenshot_path("C:/outside.jpg")

    def test_normalize_preserves_selected_bbox(self):
        state = normalize_bios_state(
            run_id="run_123",
            device_id="device_123",
            vlm_data={
                "screen_title": "OC",
                "menu_path": ["OC"],
                "cursor_at": 0,
                "entries": [
                    {"label": "CPU Lite Load", "type": "leaf-enum", "value": "Mode 9", "bbox": [1, 2, 3, 4]},
                ],
                "blocklist_flag": False,
                "blocklist_keywords": [],
            },
            screenshot_id="shot_1",
            sha256="sha_1",
            perceptual_hash="hash_1",
            resolution=[1024, 768],
            captured_at="now",
        )

        self.assertEqual(state.selection.bbox, [1, 2, 3, 4])


if __name__ == "__main__":
    unittest.main()
