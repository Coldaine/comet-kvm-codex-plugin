from __future__ import annotations
import uuid
import logging
from typing import List, Dict, Set, Optional, Tuple
from src.bios_sidecar.domain.models import BiosState, StateNode, GraphEdge, EdgeAction, EdgeEvidence
from src.bios_sidecar.domain.enums import PolicyProfile, StateKind, ControlRole
from src.bios_sidecar.policy.engine import PolicyEngine
from src.bios_sidecar.controller.observe import StateObserver
from src.bios_sidecar.controller.settle import ScreenSettler
from src.bios_sidecar.comet.client import CometClient

LOG = logging.getLogger("bios_sidecar.controller.crawl")

class BiosCrawler:
    def __init__(
        self,
        observer: StateObserver,
        policy_engine: PolicyEngine,
        settler: ScreenSettler
    ):
        self.observer = observer
        self.policy_engine = policy_engine
        self.settler = settler
        self.visited_nodes: Set[str] = set()

    async def execute_crawl_step(
        self,
        client: CometClient,
        run_id: str,
        device_id: str,
        current_state: BiosState,
        policy_profile: PolicyProfile = PolicyProfile.READ_ONLY_CRAWL
    ) -> Tuple[BiosState, Optional[GraphEdge], str]:
        """
        Executes exactly ONE safe crawl action according to DFS.
        Returns:
            (new_state, created_edge, recommendation)
        """
        LOG.info("Crawler starting step at screen: %s", current_state.location.screen_title)

        node_id = self.observer.syncer.current_matched_node.node_id if self.observer.syncer.current_matched_node else "unknown"
        self.visited_nodes.add(node_id)

        # 1. Identify candidate keys to press
        # In read_only_crawl we can press Down to scan, or Enter to descend menu lists, or Escape to go up.
        # Let's decide based on current screen type and cursor role
        candidate_key = None

        # Scan if there are submenus on the active screen
        unvisited_submenu_found = False
        selected_is_submenu = False

        for ctrl in current_state.controls:
            if ctrl.selected and ctrl.role == ControlRole.SUBMENU:
                selected_is_submenu = True

        if selected_is_submenu:
            # Let's check if the Enter action is policy-allowed
            decision = self.policy_engine.evaluate(current_state, "Enter", policy_profile)
            if decision.decision == "allowed":
                candidate_key = "Enter"
                LOG.info("Selected Enter to descend into submenu")
            else:
                LOG.warning("Enter submenu blocked by policy: %s", decision.reason)

        if not candidate_key:
            # Otherwise we click "ArrowDown" to explore other rows on this screen
            decision = self.policy_engine.evaluate(current_state, "ArrowDown", policy_profile)
            if decision.decision == "allowed":
                candidate_key = "ArrowDown"
                LOG.info("Selected ArrowDown to scan menu options")
            else:
                # If Down is blocked (or we hit boundary), can we escape up?
                decision = self.policy_engine.evaluate(current_state, "Escape", policy_profile)
                if decision.decision == "allowed":
                    candidate_key = "Escape"
                    LOG.info("Selected Escape to back up")

        if not candidate_key:
            # Safety stop
            LOG.error("No safe actions allowed by policy model! Stopping crawl.")
            return current_state, None, "stop"

        # 2. Execute action
        LOG.info("Crawl execution key: %s (profile: %s)", candidate_key, policy_profile.value)
        await client.send_combo(candidate_key)

        # 3. Wait for settle
        await self.settler.wait_for_settle(client)

        # 4. Observe next state
        new_state = await self.observer.observe_state(
            client, run_id, device_id, previous_state=current_state, last_action=candidate_key
        )
        new_node_id = self.observer.syncer.current_matched_node.node_id if self.observer.syncer.current_matched_node else "unknown"

        # 5. Populate edge if we successfully matched transition
        edge = None
        if node_id != "unknown" and new_node_id != "unknown" and node_id != new_node_id:
            edge_id = f"edge_{node_id[:6]}_{new_node_id[:6]}_{int(uuid.uuid4().hex[:6], 16)}"

            # Map capability if discovered on this node
            self._register_setting_capabilities(new_state, new_node_id)

            edge = GraphEdge(
                edge_id=edge_id,
                from_node=node_id,
                action=EdgeAction(
                    type="KEY",
                    key=candidate_key,
                    policy_decision="allowed",
                    policy_profile=policy_profile.value
                ),
                to_node=new_node_id,
                transition_type="enter_submenu" if candidate_key == "Enter" else "navigation",
                evidence=EdgeEvidence(
                    before_screenshot=current_state.frame.screenshot_id,
                    after_screenshot=new_state.frame.screenshot_id,
                    before_state=current_state.state_id,
                    after_state=new_state.state_id
                )
            )
            self.observer.syncer.matcher.graph.add_edge(edge)

        # 6. Assess crawler recommendation
        rec = "continue"
        if new_state.risk.blocklist_flag:
            LOG.warning("Crawler encountered blocklisted hazards on screen! Recommending backtrack/stop.")
            rec = "backtrack"

        return new_state, edge, rec

    def _register_setting_capabilities(self, state: BiosState, node_id: str):
        """Discovers and logs any leaf setting capabilities on the indexed node."""
        cap_index = self.observer.syncer.matcher.graph.store.list_capabilities() # read
        # Let's populate the active Capability Index in store
        from src.bios_sidecar.state.capability_index import CapabilityIndex
        idx_helper = CapabilityIndex(self.observer.store)
        for ctrl in state.controls:
            if ctrl.role == ControlRole.SETTING:
                v = ctrl.value or "unknown"
                idx_helper.register_discovered_setting(
                    ctrl.label, v, state.location.breadcrumb, node_id, ctrl.control_id
                )
