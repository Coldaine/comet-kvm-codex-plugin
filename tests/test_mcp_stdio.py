from __future__ import annotations

import asyncio
import os

import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from tests.test_smoke import EXPECTED_TOOLS, REPO_ROOT

if os.environ.get("RUN_MCP_STDIO_SMOKE") != "1":
    pytest.skip("set RUN_MCP_STDIO_SMOKE=1 to run the stdio launcher smoke test", allow_module_level=True)


def _scrubbed_launcher_env() -> dict[str, str]:
    env = {
        "HOME": os.environ.get("HOME", ""),
        "PATH": os.environ.get("PATH", ""),
        "PYTHONUNBUFFERED": "1",
        "COMET_LOG_LEVEL": "CRITICAL",
    }
    for optional_name in ("UV_CACHE_DIR", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE"):
        value = os.environ.get(optional_name)
        if value:
            env[optional_name] = value
    return env


async def _list_tools_through_locked_stdio_launcher() -> set[str]:
    params = StdioServerParameters(
        command="uv",
        args=["run", "--locked", "--python", "3.13", "python", "./glkvm_mcp.py"],
        cwd=REPO_ROOT,
        env=_scrubbed_launcher_env(),
    )
    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.list_tools()
            return {tool.name for tool in result.tools}


def test_locked_launcher_starts_and_lists_tools_without_secrets():
    tool_names = asyncio.run(asyncio.wait_for(_list_tools_through_locked_stdio_launcher(), timeout=30))
    assert EXPECTED_TOOLS <= tool_names
