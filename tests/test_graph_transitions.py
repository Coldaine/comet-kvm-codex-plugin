import unittest
from src.bios_sidecar.domain.enums import StateKind
from src.bios_sidecar.domain.models import StateNode, GraphEdge, EdgeAction, EdgeEvidence, BiosState, FrameMetadata, BiosMetadata, LocationMetadata, SelectionMetadata, ControlEntry
from src.bios_sidecar.state.store import SQLiteStore
from src.bios_sidecar.state.graph import BiosGraph
from src.bios_sidecar.state.hashing import calculate_ocr_hash
from src.bios_sidecar.state.matcher import StateMatcher
from src.bios_sidecar.state.sync import StateSyncer

class TestGraphTransitions(unittest.TestCase):
    def setUp(self):
        # Transactional SQLite memory store for isolated sandboxed test execution
        self.store = SQLiteStore(db_path=":memory:")
        self.graph = BiosGraph(self.store)

    def tearDown(self):
        self.store.close()

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

    def test_sync_uses_control_text_ocr_hash(self):
        ocr_hash = calculate_ocr_hash([{"text": "CPU Lite Load"}, {"text": "Mode 9"}])
        node = StateNode("node_ocr", "different_visual_hash", ocr_hash, "different_semantic_hash")
        self.graph.add_node(node)
        syncer = StateSyncer(StateMatcher(self.graph))
        state = BiosState(
            state_id="state_ocr",
            run_id="run_123",
            device_id="comet_123",
            frame=FrameMetadata("shot_1", "sha_1", "ffffffffffffffff", [1024, 768], "now"),
            bios=BiosMetadata("msi", "z690", "click_bios", "advanced"),
            location=LocationMetadata(StateKind.SETTING_LIST, "OC", ["OC"], "Different Screen"),
            selection=SelectionMetadata(0, "CPU Lite Load", "Mode 9"),
            controls=[ControlEntry("ctrl_0", "CPU Lite Load", "Mode 9", "setting", True, "medium")],
        )

        aligned, node_id = syncer.verify_and_align(state)
        self.assertTrue(aligned)
        self.assertEqual(node_id, "node_ocr")

if __name__ == "__main__":
    unittest.main()
