from __future__ import annotations
import uuid
import logging
from typing import List, Set, Optional, Tuple
from dataclasses import dataclass
from src.bios_sidecar.domain.models import BiosState, GraphEdge, EdgeAction, EdgeEvidence
from src.bios_sidecar.domain.enums import ControlRole
from src.bios_sidecar.controller.observe import StateObserver
from src.bios_sidecar.controller.settle import ScreenSettler
from src.kvm_core.comet.client import CometClient

LOG = logging.getLogger("bios_sidecar.controller.crawl")

# Cursor movement on the same page must not be treated as a graph cycle.
_SAME_PAGE_ACTIONS = {
    "ArrowDown",
    "ArrowUp",
    "ArrowLeft",
    "ArrowRight",
    "PageUp",
    "PageDown",
    "Tab",
    "Home",
    "End",
}


@dataclass
class CrawlEdge:
    """A pending crawl action for an edge yet to be explored."""
    action_key: str
    depth: int
    description: str = ""


class BiosCrawler:
    def __init__(
        self,
        observer: StateObserver,
        settler: ScreenSettler
    ):
        self.observer = observer
        self.settler = settler
        # DFS state, reset on each dfs_crawl start.
        self._frontier: List[CrawlEdge] = []
        self._backtrack_stack: List[str] = []  # node_ids for backtracking
        self._visited: Set[str] = set()
        # (node_id, action_key, row_index) — row_index matters for same-page cursor moves
        self._explored_actions: Set[Tuple[str, str, int]] = set()
        self._depth: int = 0
        self._max_depth: int = 8
        self._exhausted_screens: Set[str] = set()  # screens with no unexplored actions
        self._page_row_index: dict[str, int] = {}
        self._max_actions: int = 200
        self._max_wall_clock_seconds: float = 600.0
        self._actions_taken: int = 0
        self._repeated_same_node: int = 0

    def _explored_key(self, node_id: str, action_key: str, row_index: int = 0) -> Tuple[str, str, int]:
        if action_key in _SAME_PAGE_ACTIONS:
            return (node_id, action_key, row_index)
        return (node_id, action_key, 0)

    # DFS crawl loop

    async def dfs_crawl(
        self,
        client: CometClient,
        run_id: str,
        device_id: str,
        current_state: BiosState,
        max_depth: int = 8,
    ) -> Tuple[BiosState, List[GraphEdge], str]:
        """
        Full DFS crawl with frontier queue, backtrack stack, depth enforcement,
        and cycle detection.

        Returns (final_state, discovered_edges, status).
        Status: "complete" when the frontier is exhausted.
        """
        self._frontier = []
        self._backtrack_stack = []
        self._visited = set()
        self._explored_actions = set()
        self._depth = 0
        self._max_depth = max_depth
        self._exhausted_screens = set()
        self._page_row_index = {}
        self._actions_taken = 0
        self._repeated_same_node = 0
        import time
        started = time.monotonic()

        discovered_edges: List[GraphEdge] = []
        state = current_state

        # Seed: observe initial state and get/create node
        node_id = self._get_or_create_node_id(state)
        self._visited.add(node_id)
        self._enumerate_frontier(state, node_id)
        LOG.info("DFS crawl started at node=%s depth=%d frontier=%d",
                 node_id, self._depth, len(self._frontier))

        while self._frontier:
            if self._actions_taken >= self._max_actions:
                LOG.info("DFS: max_actions=%d reached", self._max_actions)
                return state, discovered_edges, "max_actions"
            if (time.monotonic() - started) >= self._max_wall_clock_seconds:
                LOG.info("DFS: wall clock limit reached")
                return state, discovered_edges, "max_wall_clock"

            # Pick highest-value unexplored edge from frontier
            next_edge = self._frontier.pop(0)
            action_key = next_edge.action_key
            row_before = self._page_row_index.get(node_id, 0)
            self._explored_actions.add(self._explored_key(node_id, action_key, row_before))
            self._actions_taken += 1

            # Backtrack if depth would exceed max
            if next_edge.depth > self._max_depth:
                LOG.info("DFS: depth %d exceeds max %d — backtracking instead of %s",
                         next_edge.depth, self._max_depth, action_key)
                state, _ = await self._backtrack_one_level(client, run_id, device_id, state)
                continue

            # Execute the action
            LOG.info("DFS crawl: depth=%d action=%s", self._depth, action_key)
            await client.send_combo(action_key)
            await self.settler.wait_for_settle(client)

            # Observe resulting state
            new_state = await self.observer.observe_state(
                client, run_id, device_id,
                previous_state=state, last_action=action_key
            )
            new_node_id = self._get_or_create_node_id(new_state)

            # Same-page cursor movement is not a page-graph cycle.
            if (
                new_node_id in self._visited
                and action_key not in _SAME_PAGE_ACTIONS
                and action_key != "Escape"
            ):
                LOG.info("DFS: cycle detected at node=%s — backtracking", new_node_id)
                self._exhausted_screens.add(node_id)
                state = new_state
                state, _ = await self._backtrack_one_level(client, run_id, device_id, state)
                continue

            if new_node_id == node_id and action_key in _SAME_PAGE_ACTIONS:
                self._repeated_same_node += 1
                self._page_row_index[node_id] = self._page_row_index.get(node_id, 0) + 1
                max_rows = max(1, len(new_state.controls) or len(state.controls))
                # Terminate same-page scan on wrap / exhausted rows, not a fixed frame cap.
                if self._page_row_index[node_id] >= max_rows:
                    LOG.info("DFS: same-page rows exhausted (%d); marking screen done", max_rows)
                    self._exhausted_screens.add(node_id)
                    self._frontier = [e for e in self._frontier if e.action_key != action_key]
                # Continue enumerating rows on this page without treating as cycle.
            else:
                self._repeated_same_node = 0

            # Record the edge only for page transitions
            if new_node_id != node_id:
                edge = self._create_edge(
                    from_node=node_id, to_node=new_node_id,
                    action_key=action_key,
                    before_state=state, after_state=new_state
                )
                if edge:
                    self.observer.syncer.matcher.graph.add_edge(edge)
                    discovered_edges.append(edge)

            # If descending (Enter), push current node to backtrack stack
            if action_key == "Enter" and new_node_id != node_id and node_id not in self._backtrack_stack:
                self._backtrack_stack.append(node_id)
                self._depth += 1

            # Register this node
            self._visited.add(new_node_id)
            state = new_state
            node_id = new_node_id

            # Enumerate frontier from this new screen
            self._enumerate_frontier(state, node_id)

            # If frontier is now empty (screen exhausted), backtrack
            if not self._frontier and self._backtrack_stack:
                LOG.info("DFS: screen %s exhausted — backtracking", node_id[:8])
                self._exhausted_screens.add(node_id)
                state, backtracked = await self._backtrack_one_level(
                    client, run_id, device_id, state
                )
                if backtracked:
                    node_id = self._get_or_create_node_id(state)

        status = "complete"
        LOG.info("DFS crawl %s: %d edges discovered, %d nodes visited",
                 status, len(discovered_edges), len(self._visited))
        return state, discovered_edges, status

    # Frontier enumeration

    def _enumerate_frontier(self, state: BiosState, node_id: str) -> None:
        """Build the frontier queue from candidate actions on this screen."""
        if node_id in self._exhausted_screens:
            return

        candidates: List[CrawlEdge] = []
        allowed_actions = self._allowed_crawl_actions(state)

        # 1. Enter on selected submenu (highest priority)
        for ctrl in state.controls:
            if (
                "Enter" in allowed_actions
                and ctrl.selected
                and ctrl.role == ControlRole.SUBMENU
            ):
                candidates.append(CrawlEdge("Enter", self._depth + 1, f"Enter {ctrl.label}"))

        # 2. ArrowDown to scan rows (medium priority) — same page, not a new node
        row_idx = self._page_row_index.get(node_id, 0)
        max_rows = max(1, len(state.controls))
        if "ArrowDown" in allowed_actions and state.controls and row_idx < max_rows:
            candidates.append(CrawlEdge("ArrowDown", self._depth, f"ArrowDown row {row_idx + 1}"))

        self._frontier = [
            candidate for candidate in candidates
            if self._explored_key(node_id, candidate.action_key, row_idx)
            not in self._explored_actions
        ]
        if not self._frontier:
            LOG.debug("DFS: no unexplored edges on node=%s", node_id[:8])

    # Backtracking

    async def _backtrack_one_level(
        self,
        client: CometClient,
        run_id: str,
        device_id: str,
        current_state: BiosState,
    ) -> Tuple[BiosState, bool]:
        """Press Escape to return to parent, re-enumerate frontier there."""
        if not self._backtrack_stack:
            return current_state, False

        parent_node = self._backtrack_stack.pop()
        self._depth = max(0, self._depth - 1)
        LOG.info("DFS backtrack: Escape to parent=%s depth=%d", parent_node[:8], self._depth)

        await client.send_combo("Escape")
        await self.settler.wait_for_settle(client)
        new_state = await self.observer.observe_state(
            client, run_id, device_id, previous_state=current_state, last_action="Escape"
        )
        new_node_id = self._get_or_create_node_id(new_state)

        # Re-enumerate frontier from parent
        self._enumerate_frontier(new_state, new_node_id)
        return new_state, True

    # Single-step crawl (keep for MCP interactive mode)

    async def execute_crawl_step(
        self,
        client: CometClient,
        run_id: str,
        device_id: str,
        current_state: BiosState,
    ) -> Tuple[BiosState, Optional[GraphEdge], str]:
        """
        Executes exactly ONE safe crawl action using DFS state tracking.
        Suitable for interactive single-step MCP tool usage.
        Returns:
            (new_state, created_edge, recommendation)
        """
        LOG.info("Crawler step at screen: %s", current_state.location.screen_title)

        node_id = self._get_or_create_node_id(current_state)
        self._visited.add(node_id)

        # Enumerate frontier if empty on this screen
        if not self._frontier:
            self._enumerate_frontier(current_state, node_id)

        # Pick candidate from frontier, or fall back to backtrack
        candidate_key = None
        if self._frontier:
            next_edge = self._frontier.pop(0)
            candidate_key = next_edge.action_key
            row_before = self._page_row_index.get(node_id, 0)
            self._explored_actions.add(self._explored_key(node_id, candidate_key, row_before))
            LOG.info("DFS step: action=%s depth=%d", candidate_key, next_edge.depth)
        elif self._backtrack_stack:
            candidate_key = "Escape"
            self._explored_actions.add(self._explored_key(node_id, candidate_key))
            LOG.info("DFS step: frontier empty — backtracking")
        else:
            # Try heuristic fallback if no DFS state initialized
            candidate_key = self._heuristic_pick(current_state)

        if not candidate_key:
            LOG.error("No crawl actions available. Stopping crawl.")
            return current_state, None, "stop"

        # 2. Execute action
        LOG.info("Crawl execution key: %s", candidate_key)
        await client.send_combo(candidate_key)

        # 3. Wait for settle
        await self.settler.wait_for_settle(client)

        # 4. Observe next state
        new_state = await self.observer.observe_state(
            client, run_id, device_id, previous_state=current_state, last_action=candidate_key
        )
        new_node_id = self._get_or_create_node_id(new_state)

        # 5. Handle backtrack
        if candidate_key == "Escape" and self._backtrack_stack:
            self._backtrack_stack.pop()
            self._depth = max(0, self._depth - 1)

        # 6. Track descent
        if candidate_key == "Enter" and node_id not in self._backtrack_stack:
            self._backtrack_stack.append(node_id)
            self._depth += 1

        rec = "continue"

        # 7. Track visited & cycle detection (same-page cursor moves are not cycles)
        if (
            new_node_id in self._visited
            and candidate_key not in _SAME_PAGE_ACTIONS
            and candidate_key != "Escape"
        ):
            LOG.info("DFS step: cycle detected at %s", new_node_id[:8])
            self._frontier = []  # clear to force backtrack next step
            rec = "backtrack"
        else:
            self._visited.add(new_node_id)
            if new_node_id == node_id and candidate_key in _SAME_PAGE_ACTIONS:
                self._page_row_index[node_id] = self._page_row_index.get(node_id, 0) + 1

        # 8. Build edge
        edge = self._create_edge(
            from_node=node_id, to_node=new_node_id,
            action_key=candidate_key,
            before_state=current_state, after_state=new_state
        )
        if edge:
            self.observer.syncer.matcher.graph.add_edge(edge)

        # 9. Re-enumerate frontier from new screen
        self._enumerate_frontier(new_state, new_node_id)

        # 10. Assess recommendation
        if not self._frontier and not self._backtrack_stack:
            rec = "complete"

        return new_state, edge, rec

    # Heuristic fallback (when DFS state not initialized)

    def _heuristic_pick(self, current_state: BiosState) -> Optional[str]:
        """Fallback single-step heuristic when no DFS state is available."""
        allowed_actions = self._allowed_crawl_actions(current_state)
        for ctrl in current_state.controls:
            if (
                "Enter" in allowed_actions
                and ctrl.selected
                and ctrl.role == ControlRole.SUBMENU
            ):
                return "Enter"

        if "ArrowDown" in allowed_actions and current_state.controls:
            return "ArrowDown"

        return "Escape" if "Escape" in allowed_actions else None

    @staticmethod
    def _allowed_crawl_actions(state: BiosState) -> Set[str]:
        """Restrict the crawler to the normalized action set for the screen."""
        if state.risk.blocklist_flag:
            return {"Escape"}
        return set(state.actions.safe) | set(state.actions.context_gated)

    # Helpers

    def _get_or_create_node_id(self, state: BiosState) -> str:
        """Get the matched node id from the syncer, or generate one."""
        if self.observer.syncer.current_matched_node:
            return self.observer.syncer.current_matched_node.node_id
        return state.state_id or f"node_{uuid.uuid4().hex[:12]}"

    def _create_edge(
        self,
        from_node: str,
        to_node: str,
        action_key: str,
        before_state: BiosState,
        after_state: BiosState,
    ) -> Optional[GraphEdge]:
        """Create a graph edge for a successful transition."""
        if from_node == "unknown" or to_node == "unknown" or from_node == to_node:
            return None

        edge_id = f"edge_{from_node[:6]}_{to_node[:6]}_{uuid.uuid4().hex[:6]}"
        self._register_setting_capabilities(after_state, to_node)

        return GraphEdge(
            edge_id=edge_id,
            from_node=from_node,
            action=EdgeAction(
                type="KEY",
                key=action_key,
            ),
            to_node=to_node,
            transition_type="enter_submenu" if action_key == "Enter" else "navigation",
            evidence=EdgeEvidence(
                before_screenshot=before_state.frame.screenshot_id,
                after_screenshot=after_state.frame.screenshot_id,
                before_state=before_state.state_id,
                after_state=after_state.state_id
            )
        )

    def _register_setting_capabilities(self, state: BiosState, node_id: str) -> None:
        """Register discovered settings in the capability index."""
        from src.bios_sidecar.state.capability_index import CapabilityIndex
        idx_helper = CapabilityIndex(self.observer.store)
        for ctrl in state.controls:
            if ctrl.role == ControlRole.SETTING:
                idx_helper.register_discovered_setting(
                    ctrl.label,
                    ctrl.value or "unknown",
                    state.location.breadcrumb,
                    node_id,
                    ctrl.control_id,
                )
