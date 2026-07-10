#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "mcp[cli]>=1.2",
#     "websockets>=12",
#     "httpx>=0.27",
#     "Pillow>=10",
#     "pytesseract>=0.3.13",
#     "instructor>=1.5",
#     "litellm>=1.50",
# ]
# ///
"""
GLKVM MCP Server
================

Composition entrypoint for the shared MCP server.

The KVM core registers universal physical-machine tools. The BIOS sidecar is an
optional layer that registers BIOS-aware tools against the same MCP instance.
"""

from __future__ import annotations

from src.kvm_core.server import mcp
import src.kvm_core.tools  # registers kvm_* and comet_* tools on the shared mcp instance
import src.bios_sidecar.mcp.server  # registers optional bios_* tools on the shared mcp instance
from src.kvm_core.logging_config import configure_logging


if __name__ == "__main__":
    import logging
    import warnings

    warnings.filterwarnings("ignore", message="Unverified HTTPS request")
    log_path = configure_logging()
    logging.getLogger("glkvm_mcp").info("Starting comet-kvm MCP server; log=%s", log_path)
    mcp.run()
