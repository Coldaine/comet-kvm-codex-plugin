from __future__ import annotations
import logging
import datetime
from typing import Optional, Dict, Any, Tuple, List
from src.bios_sidecar.domain.enums import RuntimeState, EventClass
from src.bios_sidecar.domain.models import BiosState, GraphEdge
from src.bios_sidecar.state.store import SQLiteStore
from src.bios_sidecar.state.graph import BiosGraph
from src.bios_sidecar.state.matcher import StateMatcher
from src.bios_sidecar.state.sync import StateSyncer
from src.bios_sidecar.perception.vlm_client import VLMClient
from src.bios_sidecar.controller.settle import ScreenSettler
from src.bios_sidecar.controller.observe import StateObserver
from src.bios_sidecar.controller.crawl import BiosCrawler
from src.bios_sidecar.controller.navigate import BiosNavigator
from src.bios_sidecar.controller.mutate import BiosMutator
from src.bios_sidecar.controller.recover import BiosRecoveryHandler
from src.kvm_core.runtime import get_kvm_runtime
from src.bios_sidecar.trace.ledger import TraceLedger
from src.bios_sidecar.adapters.base import BiosAdapter
from src.bios_sidecar.adapters.msi_click_bios import MsiClickBiosAdapter

LOG = logging.getLogger("bios_sidecar.controller.runtime")

# Hosts/URLs treated as non-live fixtures so unit tests can keep VLM_PROVIDER=mock.
_FIXTURE_HOST_MARKERS = (
    "192.0.2.",       # TEST-NET-1
    "198.51.100.",    # TEST-NET-2
    "203.0.113.",     # TEST-NET-3
    "127.0.0.1",
    "localhost",
    "example.com",
    "test.invalid",
)

# ── State machine transition matrix ────────────────────────────────
# Maps (current_state, method_name) → allowed
_TRANSITION_MATRIX = {
    RuntimeState.UNCONFIGURED: {
        "attach_to_kvm": RuntimeState.CONNECTED,
    },
    RuntimeState.DISCONNECTED: {
        "attach_to_kvm": RuntimeState.CONNECTED,
    },
    RuntimeState.CONNECTED: {
        "observe_state": RuntimeState.OBSERVING,
    },
    RuntimeState.OBSERVING: {
        # Transitions to SYNCED or DEGRADED based on result
    },
    RuntimeState.SYNCED: {
        "observe_state": RuntimeState.OBSERVING,
        "crawl_step": RuntimeState.CRAWLING,
        "crawl_region": RuntimeState.CRAWLING,
        "navigate_to": RuntimeState.NAVIGATING,
        "propose_setting_change": RuntimeState.SYNCED,
        "apply_setting_change": RuntimeState.MUTATING,
        "save_and_reboot": RuntimeState.MUTATING,
    },
    RuntimeState.CRAWLING: {
        "abort_and_recover": RuntimeState.RECOVERING,
    },
    RuntimeState.NAVIGATING: {
        "abort_and_recover": RuntimeState.RECOVERING,
    },
    RuntimeState.MUTATING: {
        "save_and_reboot": RuntimeState.MUTATING,
        "abort_and_recover": RuntimeState.RECOVERING,
    },
    RuntimeState.RECOVERING: {
        "observe_state": RuntimeState.OBSERVING,
    },
    RuntimeState.DEGRADED: {
        "observe_state": RuntimeState.OBSERVING,
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

        # 2. Key managers/subsystems — delegate transport/capture/OCR to KVM core
        self.kvm = get_kvm_runtime(screenshot_cache=screenshot_cache)
        self.vlm_client = VLMClient(provider=vlm_provider)

        # 3. State indexing
        self.graph = BiosGraph(store=self.store)
        self.matcher = StateMatcher(graph=self.graph)
        self.syncer = StateSyncer(matcher=self.matcher)

        # 4. Trace ledger (event-sourced audit + replay)
        self.trace = TraceLedger(store=self.store)

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
            settler=self.settler
        )
        self.navigator = BiosNavigator(
            observer=self.observer,
            settler=self.settler
        )
        self.mutator = BiosMutator(
            observer=self.observer,
            settler=self.settler
        )
        self.recovery = BiosRecoveryHandler(settler=self.settler)

        self.run_id: str = "run_unassigned"
        self.device_id: str = "device_unassigned"
        self.current_state_rec: Optional[BiosState] = None
        self._attached_client_id: Optional[int] = None

        self.state = RuntimeState.DISCONNECTED

    # ── Delegated transport (owned by KVM core) ─────────────────────
    @property
    def client(self):
        return self.kvm.client

    @property
    def capture_mgr(self):
        return self.kvm.capture_mgr

    @property
    def ocr_mgr(self):
        return self.kvm.ocr_mgr

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

    def _is_live_comet_connected(self) -> bool:
        """True when a real Comet session is up (not a test fixture host)."""
        client = self.client
        if client is None or not client.is_connected():
            return False
        host = (getattr(client, "host", "") or "").lower()
        base = (getattr(client, "base_url", "") or "").lower()
        haystack = f"{host} {base}"
        return not any(marker in haystack for marker in _FIXTURE_HOST_MARKERS)

    def refuse_mock_vlm_on_live(self) -> None:
        """
        Hard-fail bios_* observation/mutation paths when mock VLM would drive a live Comet.

        Mock mode remains valid for offline unit tests (disconnected or fixture hosts).
        Guard lives here — not inside VLMClient — so tests can still call the mock parser.
        """
        if getattr(self.vlm_client, "provider", None) != "mock":
            return
        if not self._is_live_comet_connected():
            return
        raise RuntimeError(
            "VLM_PROVIDER=mock with a live Comet connection — refusing to run "
            "bios_* tools on fabricated VLM output. Set VLM_PROVIDER to a real provider "
            "(openrouter/ollama/vllm/openai) or disconnect before using mock mode."
        )

    async def attach_to_kvm(self) -> bool:
        """Initialize BIOS-sidecar state around an existing KVM core session."""
        if self.client is None or not self.client.is_connected():
            raise RuntimeError("Not connected. Call kvm_connect first.")
        client_id = id(self.client)
        if self._attached_client_id == client_id and self.state not in (
            RuntimeState.UNCONFIGURED,
            RuntimeState.DISCONNECTED,
        ):
            return True
        if self.state in (RuntimeState.UNCONFIGURED, RuntimeState.DISCONNECTED):
            self._guard_transition("attach_to_kvm")

        host = self.client.host
        self.run_id = f"run_{datetime.datetime.now().strftime('%Y_%m_%d_%H%M%S')}"
        self.device_id = f"comet_node_{host.replace('.', '_')}"

        self.store.save_run(
            run_id=self.run_id,
            device_id=self.device_id,
            started_at=datetime.datetime.now().isoformat(),
            status="active"
        )

        self.state = RuntimeState.CONNECTED
        self.current_state_rec = None
        self._attached_client_id = client_id
        LOG.info("Stateful runtime connection established. State=CONNECTED.")
        await self.trace.log_event(
            run_id=self.run_id,
            event_type=EventClass.SESSION_CONNECTED,
            artifacts={"host": host, "device_id": self.device_id}
        )
        return True

    async def detach_from_kvm(self):
        """Clear BIOS-sidecar state without disconnecting the KVM core session."""
        self.state = RuntimeState.DISCONNECTED
        self.current_state_rec = None
        self._attached_client_id = None
        LOG.info("BIOS runtime detached from KVM. State=DISCONNECTED.")

    async def observe_state(self) -> BiosState:
        await self.attach_to_kvm()
        self.refuse_mock_vlm_on_live()
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

    async def crawl_step(self) -> Tuple[BiosState, Optional[GraphEdge], str]:
        await self.attach_to_kvm()
        self.refuse_mock_vlm_on_live()
        if self.state != RuntimeState.SYNCED or self.current_state_rec is None:
            await self.observe_state()
        self._guard_transition("crawl_step")

        self.state = RuntimeState.CRAWLING
        try:
            state_before_id = self.current_state_rec.state_id if self.current_state_rec else None
            state, edge, rec = await self.crawler.execute_crawl_step(
                self.client, self.run_id, self.device_id, self.current_state_rec
            )
            self.current_state_rec = state
            self.state = RuntimeState.SYNCED
            await self.trace.log_event(
                run_id=self.run_id,
                event_type=EventClass.ACTION_EXECUTED,
                state_before=state_before_id,
                state_after=state.state_id,
                requested_action={"type": "crawl_step"},
                artifacts={"rec": rec}
            )
            return state, edge, rec
        except Exception as e:
            self.state = RuntimeState.DEGRADED
            LOG.error("Crawler crashed: %s", e)
            raise e

    async def crawl_region(
        self,
        max_depth: int = 8,
    ) -> Tuple[BiosState, List[GraphEdge], str]:
        """
        Full DFS crawl of the current BIOS region using frontier + backtracking.
        """
        await self.attach_to_kvm()
        self.refuse_mock_vlm_on_live()
        if self.state != RuntimeState.SYNCED or self.current_state_rec is None:
            await self.observe_state()
        self._guard_transition("crawl_region")

        self.state = RuntimeState.CRAWLING
        try:
            state_before_id = self.current_state_rec.state_id if self.current_state_rec else None
            final_state, edges, status = await self.crawler.dfs_crawl(
                self.client, self.run_id, self.device_id,
                self.current_state_rec, max_depth
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

    async def navigate_to(self, target_node_id: str) -> Tuple[bool, Optional[BiosState], str]:
        await self.attach_to_kvm()
        self.refuse_mock_vlm_on_live()
        if self.state != RuntimeState.SYNCED or self.current_state_rec is None:
            await self.observe_state()
        self._guard_transition("navigate_to")

        self.state = RuntimeState.NAVIGATING
        try:
            ok, final, msg = await self.navigator.navigate_to(
                self.client, self.run_id, self.device_id, target_node_id
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
        self, capability_id: str, desired_value: str
    ) -> Tuple[bool, Optional[BiosState], str]:
        await self.attach_to_kvm()
        self.refuse_mock_vlm_on_live()
        self._guard_transition("apply_setting_change")
        self.state = RuntimeState.MUTATING
        try:
            ok, final, msg = await self.mutator.apply_setting_change(
                self.client, self.run_id, self.device_id, capability_id, desired_value
            )
            self.current_state_rec = final
            self.state = RuntimeState.SYNCED if ok else RuntimeState.DEGRADED
            await self.trace.log_event(
                run_id=self.run_id,
                event_type=EventClass.ACTION_EXECUTED,
                requested_action={"type": "mutate", "capability_id": capability_id, "desired_value": desired_value},
                state_after=final.state_id if final else None
            )
            return ok, final, msg
        except Exception as e:
            self.state = RuntimeState.DEGRADED
            LOG.error("Mutation failure: %s", e)
            raise e

    async def save_and_reboot(self) -> Tuple[bool, Optional[BiosState], str]:
        await self.attach_to_kvm()
        self.refuse_mock_vlm_on_live()
        self._guard_transition("save_and_reboot")
        self.state = RuntimeState.MUTATING
        try:
            ok, final, msg = await self.mutator.save_and_reboot(
                self.client, self.run_id, self.device_id
            )
            self.current_state_rec = final
            self.state = RuntimeState.SYNCED if ok else RuntimeState.DEGRADED
            await self.trace.log_event(
                run_id=self.run_id,
                event_type=EventClass.ACTION_EXECUTED,
                requested_action={"type": "save_and_reboot"},
                state_after=final.state_id if final else None,
            )
            return ok, final, msg
        except Exception as e:
            self.state = RuntimeState.DEGRADED
            LOG.error("Save/reboot failure: %s", e)
            raise e

    async def abort_and_recover(self) -> str:
        await self.attach_to_kvm()
        self.state = RuntimeState.RECOVERING
        res = await self.recovery.abort_and_recover(self.client)
        # Recapture state to sync point
        await self.observe_state()
        return res
