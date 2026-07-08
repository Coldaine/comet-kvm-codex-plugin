from __future__ import annotations
import os
import logging
import datetime
from typing import Optional, Dict, Any, Tuple, List
from src.bios_sidecar.domain.enums import RuntimeState, PolicyProfile, EventClass
from src.bios_sidecar.domain.models import BiosState, GraphEdge
from src.bios_sidecar.comet.client import CometClient
from src.bios_sidecar.comet.capture import CaptureManager
from src.bios_sidecar.state.store import SQLiteStore
from src.bios_sidecar.state.graph import BiosGraph
from src.bios_sidecar.state.matcher import StateMatcher
from src.bios_sidecar.state.sync import StateSyncer
from src.bios_sidecar.perception.ocr import OCRManager
from src.bios_sidecar.perception.vlm_client import VLMClient
from src.bios_sidecar.policy.approvals import ApprovalTracker
from src.bios_sidecar.policy.engine import PolicyEngine
from src.bios_sidecar.controller.settle import ScreenSettler
from src.bios_sidecar.controller.observe import StateObserver
from src.bios_sidecar.controller.crawl import BiosCrawler
from src.bios_sidecar.controller.navigate import BiosNavigator
from src.bios_sidecar.controller.mutate import BiosMutator
from src.bios_sidecar.controller.recover import BiosRecoveryHandler
from src.bios_sidecar.trace.ledger import TraceLedger
from src.bios_sidecar.adapters.base import BiosAdapter
from src.bios_sidecar.adapters.msi_click_bios import MsiClickBiosAdapter

LOG = logging.getLogger("bios_sidecar.controller.runtime")

# ── State machine transition matrix ────────────────────────────────
# Maps (current_state, method_name) → allowed
_TRANSITION_MATRIX = {
    RuntimeState.UNCONFIGURED: {
        "connect_comet": RuntimeState.CONNECTED,
    },
    RuntimeState.DISCONNECTED: {
        "connect_comet": RuntimeState.CONNECTED,
    },
    RuntimeState.CONNECTED: {
        "observe_state": RuntimeState.OBSERVING,
        "disconnect_comet": RuntimeState.DISCONNECTED,
    },
    RuntimeState.OBSERVING: {
        # Transitions to SYNCED or DEGRADED based on result
        "disconnect_comet": RuntimeState.DISCONNECTED,
    },
    RuntimeState.SYNCED: {
        "observe_state": RuntimeState.OBSERVING,
        "crawl_step": RuntimeState.CRAWLING,
        "crawl_region": RuntimeState.CRAWLING,
        "navigate_to": RuntimeState.NAVIGATING,
        "propose_setting_change": RuntimeState.SYNCED,
        "apply_setting_change": RuntimeState.MUTATING,
        "disconnect_comet": RuntimeState.DISCONNECTED,
    },
    RuntimeState.CRAWLING: {
        "disconnect_comet": RuntimeState.DISCONNECTED,
        "abort_and_recover": RuntimeState.RECOVERING,
    },
    RuntimeState.NAVIGATING: {
        "disconnect_comet": RuntimeState.DISCONNECTED,
        "abort_and_recover": RuntimeState.RECOVERING,
    },
    RuntimeState.MUTATING: {
        "disconnect_comet": RuntimeState.DISCONNECTED,
        "abort_and_recover": RuntimeState.RECOVERING,
    },
    RuntimeState.RECOVERING: {
        "observe_state": RuntimeState.OBSERVING,
        "disconnect_comet": RuntimeState.DISCONNECTED,
    },
    RuntimeState.DEGRADED: {
        "observe_state": RuntimeState.OBSERVING,
        "disconnect_comet": RuntimeState.DISCONNECTED,
        "abort_and_recover": RuntimeState.RECOVERING,
    },
    RuntimeState.AWAITING_APPROVAL: {
        "apply_setting_change": RuntimeState.MUTATING,
        "disconnect_comet": RuntimeState.DISCONNECTED,
        "abort_and_recover": RuntimeState.RECOVERING,
    },
}


class StatefulBiosRuntime:
    def __init__(
        self,
        db_path: str = "state/bios_sidecar.db",
        screenshot_cache: str = "state/screenshots",
        vlm_provider: str = "mock",
        adapter: Optional[BiosAdapter] = None,
    ):
        self.state = RuntimeState.UNCONFIGURED

        # 0. Vendor adapter (auto-detect or explicit)
        self.adapter = adapter or MsiClickBiosAdapter()

        # 1. Store
        self.store = SQLiteStore(db_path=db_path)

        # 2. Key managers/subsystems
        self.capture_mgr = CaptureManager(cache_dir=screenshot_cache)
        self.ocr_mgr = OCRManager()
        self.vlm_client = VLMClient(provider=vlm_provider)

        # 3. State indexing
        self.graph = BiosGraph(store=self.store)
        self.matcher = StateMatcher(graph=self.graph)
        self.syncer = StateSyncer(matcher=self.matcher)

        # 4. Approvals and safety policy
        self.approval_tracker = ApprovalTracker(store=self.store)
        self.policy_engine = PolicyEngine(
            approval_tracker=self.approval_tracker,
            matrix_path=os.path.join(os.path.dirname(__file__), "..", "policy", "matrix.yaml"),
            blocklist_keywords=self.adapter.hard_block_keywords,
        )

        # 5. Trace ledger (event-sourced audit + replay)
        self.trace = TraceLedger(store=self.store)

        # 6. Core execution logic helpers
        self.settler = ScreenSettler()
        self.observer = StateObserver(
            capture_mgr=self.capture_mgr,
            ocr_mgr=self.ocr_mgr,
            vlm_client=self.vlm_client,
            syncer=self.syncer,
            store=self.store
        )
        self.crawler = BiosCrawler(
            observer=self.observer,
            policy_engine=self.policy_engine,
            settler=self.settler
        )
        self.navigator = BiosNavigator(
            observer=self.observer,
            settler=self.settler
        )
        self.mutator = BiosMutator(
            observer=self.observer,
            policy_engine=self.policy_engine,
            settler=self.settler
        )
        self.recovery = BiosRecoveryHandler(settler=self.settler)

        self.client: Optional[CometClient] = None
        self.run_id: str = "run_unassigned"
        self.device_id: str = "device_unassigned"
        self.current_state_rec: Optional[BiosState] = None

        self.state = RuntimeState.DISCONNECTED

    # ── State machine guard ─────────────────────────────────────────

    def _guard_transition(self, method_name: str) -> RuntimeState:
        """
        Validate that the requested transition is allowed from the current state.
        Returns the target state if allowed, raises RuntimeError if not.
        """
        current = self.state
        allowed = _TRANSITION_MATRIX.get(current, {})
        if method_name not in allowed:
            raise RuntimeError(
                f"Invalid state transition: {current.value} → {method_name}. "
                f"Allowed from {current.value}: {list(allowed.keys())}"
            )
        return allowed[method_name]

    async def connect_comet(self, host: str, pswd: str, username: str = "admin") -> bool:
        if self.client:
            await self.disconnect_comet()
        self._guard_transition("connect_comet")

        self.client = CometClient(host=host, username=username, password=pswd)
        await self.client.connect()

        # Update connection states
        self.run_id = f"run_{datetime.datetime.now().strftime('%Y_%m_%d_%H%M%S')}"
        self.device_id = f"comet_node_{host.replace('.', '_')}"

        self.store.save_run(
            run_id=self.run_id,
            device_id=self.device_id,
            started_at=datetime.datetime.now().isoformat(),
            status="active"
        )

        self.state = RuntimeState.CONNECTED
        LOG.info("Stateful runtime connection established. State=CONNECTED.")
        await self.trace.log_event(
            run_id=self.run_id,
            event_type=EventClass.SESSION_CONNECTED,
            artifacts={"host": host, "device_id": self.device_id}
        )
        return True

    async def disconnect_comet(self):
        if self.client:
            await self.client.disconnect()
            self.client = None
        self.state = RuntimeState.DISCONNECTED
        LOG.info("Stateful runtime disconnected. State=DISCONNECTED.")

    async def observe_state(self) -> BiosState:
        if self.client is None or not self.client.is_connected():
            raise RuntimeError("Not connected. Call bios_connect or kvm_connect first.")
        self._guard_transition("observe_state")

        self.state = RuntimeState.OBSERVING
        try:
            res = await self.observer.observe_state(
                self.client, self.run_id, self.device_id, previous_state=self.current_state_rec
            )
            self.current_state_rec = res
            self.state = RuntimeState.SYNCED if self.syncer.is_synced else RuntimeState.DEGRADED
            await self.trace.log_event(
                run_id=self.run_id,
                event_type=EventClass.STATE_NORMALIZED,
                state_after=res.state_id,
                artifacts={"screenshot_id": res.frame.screenshot_id, "state_kind": res.location.screen_kind.value}
            )
            return res
        except Exception as e:
            self.state = RuntimeState.DEGRADED
            LOG.error("Failure encountered in observe step: %s", e)
            raise e

    async def crawl_step(self, policy_profile: PolicyProfile = PolicyProfile.READ_ONLY_CRAWL) -> Tuple[BiosState, Optional[GraphEdge], str]:
        if self.client is None or not self.client.is_connected():
            raise RuntimeError("Not connected.")
        if self.state != RuntimeState.SYNCED or self.current_state_rec is None:
            await self.observe_state()
        self._guard_transition("crawl_step")

        self.state = RuntimeState.CRAWLING
        try:
            state_before_id = self.current_state_rec.state_id if self.current_state_rec else None
            state, edge, rec = await self.crawler.execute_crawl_step(
                self.client, self.run_id, self.device_id, self.current_state_rec, policy_profile
            )
            self.current_state_rec = state
            self.state = RuntimeState.SYNCED
            await self.trace.log_event(
                run_id=self.run_id,
                event_type=EventClass.ACTION_EXECUTED,
                state_before=state_before_id,
                state_after=state.state_id,
                requested_action={"type": "crawl_step", "policy_profile": policy_profile.value},
                artifacts={"rec": rec}
            )
            return state, edge, rec
        except Exception as e:
            self.state = RuntimeState.DEGRADED
            LOG.error("Crawler crashed: %s", e)
            raise e

    async def crawl_region(
        self,
        policy_profile: PolicyProfile = PolicyProfile.READ_ONLY_CRAWL,
        max_depth: int = 8,
    ) -> Tuple[BiosState, List[GraphEdge], str]:
        """
        Full DFS crawl of the current BIOS region using frontier + backtracking.
        """
        if self.client is None or not self.client.is_connected():
            raise RuntimeError("Not connected.")
        if self.state != RuntimeState.SYNCED or self.current_state_rec is None:
            await self.observe_state()
        self._guard_transition("crawl_region")

        self.state = RuntimeState.CRAWLING
        try:
            state_before_id = self.current_state_rec.state_id if self.current_state_rec else None
            final_state, edges, status = await self.crawler.dfs_crawl(
                self.client, self.run_id, self.device_id,
                self.current_state_rec, policy_profile, max_depth
            )
            self.current_state_rec = final_state
            self.state = RuntimeState.SYNCED if status == "complete" else RuntimeState.DEGRADED
            await self.trace.log_event(
                run_id=self.run_id,
                event_type=EventClass.ACTION_EXECUTED,
                state_before=state_before_id,
                state_after=final_state.state_id,
                requested_action={"type": "crawl_region", "depth": max_depth, "status": status},
                artifacts={"edges_discovered": len(edges)}
            )
            return final_state, edges, status
        except Exception as e:
            self.state = RuntimeState.DEGRADED
            LOG.error("DFS crawl failed: %s", e)
            raise e

    async def navigate_to(self, target_node_id: str, policy_profile: PolicyProfile = PolicyProfile.READ_ONLY_CRAWL) -> Tuple[bool, Optional[BiosState], str]:
        if self.client is None or not self.client.is_connected():
            raise RuntimeError("Not connected.")
        if self.state != RuntimeState.SYNCED or self.current_state_rec is None:
            await self.observe_state()
        self._guard_transition("navigate_to")

        self.state = RuntimeState.NAVIGATING
        try:
            ok, final, msg = await self.navigator.navigate_to(
                self.client, self.run_id, self.device_id, target_node_id, policy_profile
            )
            self.current_state_rec = final
            self.state = RuntimeState.SYNCED if ok else RuntimeState.DEGRADED
            return ok, final, msg
        except Exception as e:
            self.state = RuntimeState.DEGRADED
            LOG.error("Navigation error: %s", e)
            raise e

    async def propose_setting_change(self, capability_id: str, desired_value: str) -> Dict[str, Any]:
        return await self.mutator.propose_setting_change(capability_id, desired_value)

    async def apply_setting_change(
        self, plan_id: str, approval_id: str, capability_id: str, desired_value: str
    ) -> Tuple[bool, Optional[BiosState], str]:
        if self.client is None or not self.client.is_connected():
            raise RuntimeError("Not connected.")
        self._guard_transition("apply_setting_change")
        self.state = RuntimeState.MUTATING
        try:
            ok, final, msg = await self.mutator.apply_setting_change(
                self.client, self.run_id, self.device_id, plan_id, approval_id, capability_id, desired_value
            )
            self.current_state_rec = final
            self.state = RuntimeState.SYNCED if ok else RuntimeState.DEGRADED
            await self.trace.log_event(
                run_id=self.run_id,
                event_type=EventClass.APPROVAL_GRANTED,
                requested_action={"type": "mutate", "capability_id": capability_id, "desired_value": desired_value},
                policy_decision={"plan_id": plan_id, "approval_id": approval_id, "success": ok},
                state_after=final.state_id if final else None
            )
            return ok, final, msg
        except Exception as e:
            self.state = RuntimeState.DEGRADED
            LOG.error("Mutation failure: %s", e)
            raise e

    async def abort_and_recover(self) -> str:
        if self.client is None or not self.client.is_connected():
            raise RuntimeError("Not connected. Call bios_connect or kvm_connect first.")
        self.state = RuntimeState.RECOVERING
        res = await self.recovery.abort_and_recover(self.client)
        # Recapture state to sync point
        await self.observe_state()
        return res
