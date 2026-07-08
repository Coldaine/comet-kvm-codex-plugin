from __future__ import annotations
import collections
import logging
from typing import List, Dict, Tuple, Optional
from src.bios_sidecar.domain.models import StateNode, GraphEdge
from src.bios_sidecar.state.store import SQLiteStore

LOG = logging.getLogger("bios_sidecar.state.graph")

class BiosGraph:
    def __init__(self, store: SQLiteStore):
        self.store = store
        self.nodes: Dict[str, StateNode] = {}
        self.edges: List[GraphEdge] = []
        self.reload_from_store()

    def reload_from_store(self):
        self.nodes = {n.node_id: n for n in self.store.list_nodes()}
        self.edges = self.store.list_edges()
        LOG.info("Loaded %d nodes and %d edges from store", len(self.nodes), len(self.edges))

    def add_node(self, node: StateNode):
        if node.node_id not in self.nodes:
            self.nodes[node.node_id] = node
            self.store.save_node(node)
            LOG.info("Added state node %s to graph", node.node_id)

    def add_edge(self, edge: GraphEdge):
        # Ensure both endpoint nodes exist — reject orphaned edges rather than silently inserting.
        missing = [n for n in (edge.from_node, edge.to_node) if n not in self.nodes]
        if missing:
            raise ValueError(
                f"Cannot add edge {edge.edge_id!r}: node(s) {missing} not found in graph. "
                "Add both endpoint nodes before adding the edge."
            )

        # Avoid duplicate edges
        exists = any(
            e.from_node == edge.from_node and e.to_node == edge.to_node and e.action.key == edge.action.key
            for e in self.edges
        )
        if not exists:
            self.edges.append(edge)
            self.store.save_edge(edge)
            LOG.info("Added transition edge %s (%s -> %s)", edge.edge_id, edge.from_node, edge.to_node)

    def find_shortest_path(self, start_node_id: str, target_node_id: str) -> Optional[List[GraphEdge]]:
        """
        Calculates the shortest key sequence from start_node to target_node using BFS.
        Each node is represented by its node_id.
        """
        if start_node_id not in self.nodes or target_node_id not in self.nodes:
            return None

        if start_node_id == target_node_id:
            return []

        # Map parent links for BFS path reconstruction
        queue = collections.deque([start_node_id])
        visited = {start_node_id}
        parent_map: Dict[str, Tuple[str, GraphEdge]] = {}  # child -> (parent, edge)

        while queue:
            curr = queue.popleft()
            if curr == target_node_id:
                break

            # Find all outgoing edges from curr
            for edge in self.edges:
                if edge.from_node == curr:
                    nbr = edge.to_node
                    if nbr not in visited:
                        visited.add(nbr)
                        parent_map[nbr] = (curr, edge)
                        queue.append(nbr)

        if target_node_id not in parent_map:
            return None  # No path reachable

        # Reconstruct path of edges
        path = []
        curr = target_node_id
        while curr != start_node_id:
            parent, edge = parent_map[curr]
            path.append(edge)
            curr = parent

        path.reverse()
        return path

    def detect_cycles(self) -> List[List[str]]:
        """Returns lists of node IDs that form cycles in the graph (DFS back-edges)."""
        visited = {}  # node -> 0: unvisited, 1: visiting, 2: visited
        for k in self.nodes:
            visited[k] = 0

        cycles = []
        path = []

        def dfs(node_id: str):
            visited[node_id] = 1
            path.append(node_id)

            for edge in self.edges:
                if edge.from_node == node_id:
                    nbr = edge.to_node
                    if visited.get(nbr, 0) == 1:
                        # cycle found, extract cycle path
                        cycle_start_idx = path.index(nbr)
                        cycles.append(list(path[cycle_start_idx:]))
                    elif visited.get(nbr, 0) == 0:
                        dfs(nbr)

            path.pop()
            visited[node_id] = 2

        for node in self.nodes:
            if visited[node] == 0:
                dfs(node)

        return cycles
