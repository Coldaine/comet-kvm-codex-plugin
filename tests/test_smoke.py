"""
Smoke test for glkvm_mcp.py.

Imports the server module without launching the stdio loop and asserts that the
expected MCP tools are registered. Run from the repo root:

    python -m unittest tests.test_smoke

or directly:

    python tests/test_smoke.py
"""
from __future__ import annotations

import asyncio
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
SERVER_PATH = os.path.join(REPO_ROOT, "glkvm_mcp.py")
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

_SERVER_MODULE = None

EXPECTED_TOOLS = {
    "kvm_connect",
    "kvm_disconnect",
    "kvm_send_text",
    "kvm_send_keys",
    "kvm_hold_key",
    "kvm_release_all",
    "kvm_mouse_move",
    "kvm_mouse_move_pct",
    "kvm_mouse_click",
    "kvm_mouse_scroll",
    "kvm_screenshot",
    "kvm_screenshot_to_file",
    "kvm_status",
    # Deprecated raw aliases remain public compatibility API.
    "comet_raw_send_text",
    "comet_raw_send_keys",
    "comet_raw_hold_key",
    "comet_raw_release_all",
    "comet_raw_mouse_move",
    "comet_raw_mouse_move_pct",
    "comet_raw_mouse_click",
    "comet_raw_mouse_scroll",
    "comet_raw_screenshot",
    "comet_raw_status",
    # Tier 1 stateful BIOS tools
    "bios_observe_state",
    "bios_crawl_region",
    "bios_navigate_to",
    "bios_propose_setting_change",
    "bios_apply_setting_change",
    "bios_save_and_reboot",
    "bios_abort_and_recover",
    "bios_export_trace",
    # Tier 3 perception + raw namespace
    "kvm_vlm_parse",
    "kvm_match_screen",
}


def _load_module():
    global _SERVER_MODULE
    if _SERVER_MODULE is not None:
        return _SERVER_MODULE
    spec = importlib.util.spec_from_file_location("glkvm_mcp", SERVER_PATH)
    assert spec is not None and spec.loader is not None, "could not load glkvm_mcp.py"
    mod = importlib.util.module_from_spec(spec)
    sys.modules["glkvm_mcp"] = mod
    spec.loader.exec_module(mod)
    _SERVER_MODULE = mod
    return mod


class SmokeTest(unittest.TestCase):
    def test_module_imports(self):
        mod = _load_module()
        self.assertTrue(hasattr(mod, "mcp"), "module should expose `mcp` (FastMCP instance)")

    def test_tools_registered(self):
        mod = _load_module()
        tools = asyncio.run(mod.mcp.list_tools())
        names = {t.name for t in tools}
        missing = EXPECTED_TOOLS - names
        self.assertFalse(
            missing,
            msg=f"Missing tools: {sorted(missing)}. Got: {sorted(names)}",
        )

    def test_kvm_connect_signature(self):
        mod = _load_module()
        tools = asyncio.run(mod.mcp.list_tools())
        connect = next((t for t in tools if t.name == "kvm_connect"), None)
        self.assertIsNotNone(connect, "kvm_connect tool not registered")
        schema = connect.inputSchema
        required = set(schema.get("required", []))
        self.assertEqual(
            required, {"host", "password"},
            msg=f"kvm_connect required args should be host+password, got {required}",
        )
        username_default = schema.get("properties", {}).get("username", {}).get("default")
        self.assertEqual(
            username_default, "admin",
            msg=f"kvm_connect username should default to 'admin', got {username_default!r}",
        )

    def test_kvm_core_tools_do_not_import_sidecar(self):
        code = """
import asyncio
import sys
import src.kvm_core.tools
from src.kvm_core.server import mcp
tool_names = {tool.name for tool in asyncio.run(mcp.list_tools())}
assert not any(name.startswith('bios_') for name in tool_names), sorted(tool_names)
assert not any(name.startswith('src.bios_sidecar') for name in sys.modules), 'sidecar imported by kvm core'
"""
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)

    def test_sidecar_runtime_reconfigures_existing_kvm_cache(self):
        from src.bios_sidecar.controller.runtime import StatefulBiosRuntime
        import src.kvm_core.runtime as kvm_runtime

        with tempfile.TemporaryDirectory() as temp_dir:
            initial_cache = os.path.join(temp_dir, "initial-screenshots")
            requested_cache = os.path.join(temp_dir, "requested-screenshots")
            with patch.object(
                kvm_runtime,
                "_runtime",
                kvm_runtime.KVMRuntime(screenshot_cache=initial_cache),
            ):
                runtime = StatefulBiosRuntime(
                    db_path=":memory:",
                    screenshot_cache=requested_cache,
                )

                self.assertEqual(runtime.capture_mgr.cache_dir, requested_cache)

    def test_msd_upload_preserves_file_read_error_as_cause(self):
        import src.kvm_core.tools as kvm_tools

        with tempfile.TemporaryDirectory() as temp_dir:
            missing_path = os.path.join(temp_dir, "missing.iso")
            with patch.object(kvm_tools, "_require_client", return_value=object()):
                with self.assertRaises(ValueError) as raised:
                    asyncio.run(kvm_tools.comet_msd_upload("images/missing.iso", missing_path))

        self.assertIsInstance(raised.exception.__cause__, FileNotFoundError)


if __name__ == "__main__":
    unittest.main(verbosity=2)
