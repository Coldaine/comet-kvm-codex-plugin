from __future__ import annotations
import os
import json
import logging
import asyncio
from typing import Dict, Any, List, Optional
from mcp.server.fastmcp import FastMCP, Image
from src.bios_sidecar.domain.enums import PolicyProfile
from src.bios_sidecar.controller.runtime import StatefulBiosRuntime

LOG = logging.getLogger("bios_sidecar.mcp")

# Initialize unified server instance
mcp = FastMCP("glkvm_sidecar")

# Global runtime state instance
_runtime: Optional[StatefulBiosRuntime] = None

def get_runtime() -> StatefulBiosRuntime:
    global _runtime
    if _runtime is None:
        _runtime = StatefulBiosRuntime()
    return _runtime

# ===========================================================================
# 1. MCP Resources
# ===========================================================================

@mcp.resource("bios://state/current")
def get_current_state() -> str:
    """Latest normalized BIOS state."""
    r = get_runtime()
    if r.current_state_rec:
        return json.dumps(r.current_state_rec.to_dict(), indent=2)
    return json.dumps({"connected": False, "state": "No state observed yet. Call bios_observe_state first."})

@mcp.resource("bios://screen/current")
def get_current_screen() -> bytes:
    """Current screenshot."""
    # Read the latest temp screenshot file if exists
    r = get_runtime()
    if r.current_state_rec:
        shot_id = r.current_state_rec.frame.screenshot_id
        path = os.path.join(r.capture_mgr.cache_dir, f"{shot_id}.jpg")
        if os.path.exists(path):
            with open(path, "rb") as f:
                return f.read()
    return b""

@mcp.resource("bios://graph/current")
def get_graph_summary() -> str:
    """BIOS Navigation graph summary."""
    r = get_runtime()
    nodes = list(r.graph.nodes.keys())
    edges = [f"{e.from_node} -> {e.action.key} -> {e.to_node}" for e in r.graph.edges]
    return json.dumps({
        "node_count": len(nodes),
        "nodes": nodes,
        "edge_count": len(edges),
        "edges": edges
    }, indent=2)

@mcp.resource("bios://capabilities/current")
def get_capabilities_resource() -> str:
    """Discovered settings capabilities list."""
    r = get_runtime()
    caps = r.store.list_capabilities()
    return json.dumps([c.to_dict() for c in caps], indent=2)

@mcp.resource("bios://policy/current")
def get_active_policy() -> str:
    """Safety action matrix definitions."""
    r = get_runtime()
    return json.dumps(r.policy_engine.matrix, indent=2)

# ===========================================================================
# 2. Stateful MCP Tools (the main agent-facing interface)
# ===========================================================================

@mcp.tool()
async def bios_connect(host: str, password: str, username: str = "admin") -> dict:
    """
    Connect stateful runtime to a physical Comet KVM session on LAN.
    """
    r = get_runtime()
    ok = await r.connect_comet(host, password, username)
    return {"connected": ok, "run_id": r.run_id, "device_id": r.device_id}

@mcp.tool()
async def bios_disconnect() -> dict:
    """Disconnect session and release resources."""
    r = get_runtime()
    await r.disconnect_comet()
    return {"status": "disconnected"}

@mcp.tool()
async def bios_observe_state() -> dict:
    """
    Observe, capture, and fully parse current BIOS. Updates navigation syncer.
    """
    r = get_runtime()
    state = await r.observe_state()
    return state.to_dict()

@mcp.tool()
async def bios_crawl_step(policy_profile: str = "read_only_crawl") -> dict:
    """
    Execute ONE safe crawling transition step to discover submenus & settings.
    """
    profile = PolicyProfile(policy_profile)
    r = get_runtime()
    state, edge, rec = await r.crawl_step(profile)
    return {
        "state": state.to_dict(),
        "created_edge": edge.to_dict() if edge else None,
        "recommendation": rec
    }

@mcp.tool()
async def bios_crawl_region(max_depth: int = 8, policy_profile: str = "read_only_crawl") -> dict:
    """
    Full DFS crawl with frontier queue, backtrack stack, depth enforcement,
    and cycle detection. Explores the current BIOS region exhaustively.
    """
    r = get_runtime()
    profile = PolicyProfile(policy_profile)
    final_state, edges, status = await r.crawl_region(profile, max_depth)
    return {
        "status": status,
        "edges_discovered_count": len(edges),
        "edges": [e.to_dict() for e in edges],
        "final_state": final_state.to_dict()
    }

@mcp.tool()
async def bios_navigate_to(target_node_id: str) -> dict:
    """
    Deterministic path execution. Uses stored graph routes to navigates to an indexed node.
    """
    r = get_runtime()
    ok, final, msg = await r.navigate_to(target_node_id)
    return {
        "success": ok,
        "final_state": final.to_dict() if final else None,
        "message": msg
    }

@mcp.tool()
async def bios_propose_setting_change(capability_id: str, desired_value: str) -> dict:
    """
    Validate, plan, and propose a setting alteration. Generates approval tokens.
    """
    r = get_runtime()
    res = await r.propose_setting_change(capability_id, desired_value)
    return res

@mcp.tool()
async def bios_apply_setting_change(plan_id: str, approval_id: str, capability_id: str, desired_value: str) -> dict:
    """
    Executes an approved mutation. Verifies old value, switches value, captures post confirmations.
    """
    r = get_runtime()
    ok, final, msg = await r.apply_setting_change(plan_id, approval_id, capability_id, desired_value)
    return {
        "success": ok,
        "state": final.to_dict() if final else None,
        "message": msg
    }

@mcp.tool()
async def bios_grant_human_approval(approval_id: str, approved_by: str = "operator") -> dict:
    """
    Grants/authorizes a pending mutation approval.
    """
    r = get_runtime()
    ok = r.policy_engine.approval_tracker.grant_approval(approval_id, approved_by)
    return {"granted": ok, "approval_id": approval_id}

@mcp.tool()
async def bios_abort_and_recover() -> dict:
    """Releases active key holds, Consecutive Escape presses to back-out of modals."""
    r = get_runtime()
    res = await r.abort_and_recover()
    return {"status": res}

@mcp.tool()
async def bios_export_trace() -> dict:
    """Exports a replayable run trace log file."""
    r = get_runtime()
    from src.bios_sidecar.trace.ledger import TraceLedger
    ledger = TraceLedger(r.store)
    file_path = ledger.export_run_trace_json(r.run_id)
    return {"trace_file": file_path, "bytes": os.path.getsize(file_path)}
