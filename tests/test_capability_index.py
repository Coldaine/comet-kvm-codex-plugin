import unittest
from src.bios_sidecar.state.store import SQLiteStore
from src.bios_sidecar.state.capability_index import CapabilityIndex

class TestCapabilityIndex(unittest.TestCase):
    def setUp(self):
        self.store = SQLiteStore(db_path=":memory:")
        self.index = CapabilityIndex(self.store)

    def test_priors_loaded_automatically(self):
        # Priors are pre-populated on empty creation
        cpu_lite = self.index.resolve_capability_by_handle("cpu_lite_load_mode")
        self.assertIsNotNone(cpu_lite)
        self.assertEqual(cpu_lite.canonical_name, "CPU Lite Load Mode")
        self.assertEqual(cpu_lite.risk.value, "medium")

    def test_alias_resolution(self):
        # Resolve by alias
        cpu_lite = self.index.resolve_capability_by_handle("CPU Lite Load Control")
        self.assertIsNotNone(cpu_lite)
        self.assertEqual(cpu_lite.capability_id, "cpu_lite_load_mode")

    def test_new_capability_registration(self):
        # Register a totally new custom setting seen on-the-fly
        self.index.register_discovered_setting(
            "XMP Profile 1", "Enabled", ["OC", "DRAM Settings"], "node_main_oc", "ctrl_0"
        )

        resolved = self.index.resolve_capability_by_handle("XMP Profile 1")
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.canonical_name, "XMP Profile 1")
        self.assertEqual(len(resolved.paths), 1)
        self.assertEqual(resolved.paths[0].node_id, "node_main_oc")
        self.assertEqual(resolved.paths[0].last_seen_value, "Enabled")

if __name__ == "__main__":
    unittest.main()
