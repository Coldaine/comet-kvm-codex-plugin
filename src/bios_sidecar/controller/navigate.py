from __future__ import annotations
import logging
from typing import List, Optional, Tuple
from src.bios_sidecar.domain.models import BiosState, GraphEdge
from src.bios_sidecar.domain.enums import ControlRole
from src.bios_sidecar.controller.observe import StateObserver
from src.bios_sidecar.controller.settle import ScreenSettler
from src.kvm_core.comet.client import CometClient

LOG = logging.getLogger("bios_sidecar.controller.navigate")

class BiosNavigator:
    def __init__(
        self,
        observer: StateObserver,
        settler: ScreenSettler
    ):
        self.observer = observer
        self.settler = settler

    async def navigate_to(
        self,
        client: CometClient,
        run_id: str,
        device_id: str,
        target_node_id: str,
    ) -> Tuple[bool, Optional[BiosState], str]:
        """
        Uses graph shortest path routing to reach target_node_id.
        Verifies and asserts alignment during intermediate hops.
        Returns:
            (success, final_observed_state, message)
        """
        # Ensure we are synced first
        if not self.observer.syncer.is_synced or not self.observer.syncer.current_matched_node:
            return False, None, "Tracker not synced. Observe state first."

        start_node_id = self.observer.syncer.current_matched_node.node_id
        if start_node_id == target_node_id:
            # We are already there
            # Get latest current state
            state = await self.observer.observe_state(client, run_id, device_id)
            return True, state, "Already at target node."

        graph = self.observer.syncer.matcher.graph
        path = graph.find_shortest_path(start_node_id, target_node_id)
        if path is None:
            return False, None, f"No path found in graph from node {start_node_id} to node {target_node_id}."

        LOG.info("Calculating shortest path pathway: %d edge hops.", len(path))
        current_state = None

        for hop_idx, edge in enumerate(path):
            action_key = edge.action.key
            LOG.info("Executing hop %d/%d: keypress %s to transition to node %s",
                     hop_idx + 1, len(path), action_key, edge.to_node)

            # Execute step transition
            await client.send_combo(action_key)
            await self.settler.wait_for_settle(client)

            # Observe state to verify alignment
            current_state = await self.observer.observe_state(
                client, run_id, device_id, previous_state=current_state, last_action=action_key
            )

            # Check for drift
            aligned = self.observer.syncer.is_synced
            curr_matched = self.observer.syncer.current_matched_node.node_id if self.observer.syncer.current_matched_node else "unknown"

            if not aligned or curr_matched != edge.to_node:
                LOG.error("Path drift detected at hop %d! Expected to match node %s but tracker matched %s",
                          hop_idx + 1, edge.to_node, curr_matched)
                return False, current_state, f"Path drift detected at hop {hop_idx+1}. Mismatched screen."

        return True, current_state, "Successfully navigated to target node."
