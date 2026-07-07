import unittest
from src.bios_sidecar.domain.models import StateNode, GraphEdge, EdgeAction, EdgeEvidence
from src.bios_sidecar.state.store import SQLiteStore
from src.bios_sidecar.state.graph import BiosGraph

class TestGraphTransitions(unittest.TestCase):
    def setUp(self):
        # Transactional SQLite memory store for isolated sandboxed test execution
        self.store = SQLiteStore(db_path=":memory:")
        self.graph = BiosGraph(self.store)

    def test_shortest_path_simple(self):
        # Insert 3 nodes forming a line: NodeA ->(Enter)-> NodeB ->(Down)-> NodeC
        n1 = StateNode("node_A", "hash_a", "ocr_a", "sem_a")
        n2 = StateNode("node_B", "hash_b", "ocr_b", "sem_b")
        n3 = StateNode("node_C", "hash_c", "ocr_c", "sem_c")

        self.graph.add_node(n1)
        self.graph.add_node(n2)
        self.graph.add_node(n3)

        e1 = GraphEdge("edge1", "node_A", EdgeAction("KEY", "Enter"), "node_B", "enter", EdgeEvidence("s1", "s2", "sa", "sb"))
        e2 = GraphEdge("edge2", "node_B", EdgeAction("KEY", "ArrowDown"), "node_C", "nav", EdgeEvidence("s2", "s3", "sb", "sc"))

        self.graph.add_edge(e1)
        self.graph.add_edge(e2)

        # Retrieve paths from A to C
        path = self.graph.find_shortest_path("node_A", "node_C")
        self.assertIsNotNone(path)
        self.assertEqual(len(path), 2)
        self.assertEqual(path[0].edge_id, "edge1")
        self.assertEqual(path[1].edge_id, "edge2")

    def test_cycle_detection(self):
        # A -> B -> A cycle
        n1 = StateNode("node_A", "hash_a", "ocr_a", "sem_a")
        n2 = StateNode("node_B", "hash_b", "ocr_b", "sem_b")
        self.graph.add_node(n1)
        self.graph.add_node(n2)

        e1 = GraphEdge("edge1", "node_A", EdgeAction("KEY", "Enter"), "node_B", "enter", EdgeEvidence("s1","s2","sa","sb"))
        e2 = GraphEdge("edge2", "node_B", EdgeAction("KEY", "Escape"), "node_A", "escape", EdgeEvidence("s2","s1","sb","sa"))
        self.graph.add_edge(e1)
        self.graph.add_edge(e2)

        cycles = self.graph.detect_cycles()
        self.assertTrue(len(cycles) > 0)
        self.assertTrue("node_A" in cycles[0])
        self.assertTrue("node_B" in cycles[0])

if __name__ == "__main__":
    unittest.main()
