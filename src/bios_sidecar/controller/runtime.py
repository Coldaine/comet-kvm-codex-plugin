from __future__ import annotations
import logging
import datetime
from typing import Optional, Dict, Any, Tuple
from src.bios_sidecar.domain.enums import RuntimeState, PolicyProfile
from src.bios_sidecar.domain.models import BiosState
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

LOG = logging.getLogger("bios_sidecar.controller.runtime")

class StatefulBiosRuntime:
    def __init__(self, db_path: str = "state/bios_sidecar.db", screenshot_cache: str = "state/screenshots", vlm_provider: str = "mock"):
        self.state = RuntimeState.UNCONFIGURED

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
        self.policy_engine = PolicyEngine(approval_tracker=self.approval_tracker)

        # 5. Core execution logic helpers
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

    async def connect_comet(self, host: str, pswd: str, username: str = "admin") -> bool:
        if self.client:
            await self.disconnect_comet()

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
        return True

    async def disconnect_comet(self):
        if self.client:
            await self.client.disconnect()
            self.client = None
        self.state = RuntimeState.DISCONNECTED
        LOG.info("Stateful runtime disconnected. State=DISCONNECTED.")

    async def observe_state(self) -> BiosState:
        if self.state not in (RuntimeState.CONNECTED, RuntimeState.SYNCED, RuntimeState.OBSERVING):
            # Tolerate observing in active crawlers
            pass

        old_state = self.state
        self.state = RuntimeState.OBSERVING

        try:
            res = await self.observer.observe_state(
                self.client, self.run_id, self.device_id, previous_state=self.current_state_rec
            )
            self.current_state_rec = res
            self.state = RuntimeState.SYNCED if self.syncer.is_synced else RuntimeState.DEGRADED
            return res
        except Exception as e:
            self.state = RuntimeState.DEGRADED
            LOG.error("Failure encountered in observe step: %s", e)
            raise e

    async def crawl_step(self, policy_profile: PolicyProfile = PolicyProfile.READ_ONLY_CRAWL) -> Tuple[BiosState, Optional[GraphEdge], str]:
        if self.state != RuntimeState.SYNCED:
            # Re-observe first to align tracker
            await self.observe_state()

        self.state = RuntimeState.CRAWLING
        try:
            state, edge, rec = await self.crawler.execute_crawl_step(
                self.client, self.run_id, self.device_id, self.current_state_rec, policy_profile
            )
            self.current_state_rec = state
            self.state = RuntimeState.SYNCED
            return state, edge, rec
        except Exception as e:
            self.state = RuntimeState.DEGRADED
            LOG.error("Crawler crashed: %s", e)
            raise e

    async def navigate_to(self, target_node_id: str, policy_profile: PolicyProfile = PolicyProfile.READ_ONLY_CRAWL) -> Tuple[bool, BiosState, str]:
        if self.state != RuntimeState.SYNCED:
            await self.observe_state()

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
        self.state = RuntimeState.MUTATING
        try:
            ok, final, msg = await self.mutator.apply_setting_change(
                self.client, self.run_id, self.device_id, plan_id, approval_id, capability_id, desired_value
            )
            self.current_state_rec = final
            self.state = RuntimeState.SYNCED if ok else RuntimeState.DEGRADED
            return ok, final, msg
        except Exception as e:
            self.state = RuntimeState.DEGRADED
            LOG.error("Mutation failure: %s", e)
            raise e

    async def abort_and_recover(self) -> str:
        self.state = RuntimeState.RECOVERING
        res = await self.recovery.abort_and_recover(self.client)
        # Recapture state to sync point
        await self.observe_state()
        return res
