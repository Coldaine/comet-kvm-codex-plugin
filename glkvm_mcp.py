#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "mcp[cli]>=1.28,<2",
#     "websockets>=16.1",
#     "httpx>=0.28.1",
#     "Pillow>=12.3.0",
#     "pytesseract>=0.3.13",
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

import os

from src.kvm_core.server import mcp

# Side-effect imports register tools against the shared FastMCP instance.
import src.kvm_core.tools  # noqa: F401

# BIOS sidecar loads by default (bios_* tools on the same MCP process). Set
# COMET_DISABLE_BIOS_SIDECAR=1 to skip the import for a KVM-core-only server.
if os.environ.get("COMET_DISABLE_BIOS_SIDECAR", "").strip().lower() not in (
    "1",
    "true",
    "yes",
):
    import src.bios_sidecar.mcp.server  # noqa: F401

from src.kvm_core.logging_config import configure_logging


if __name__ == "__main__":
    import logging
    import warnings
    import sys

    if "--expect-tesseract" in sys.argv:
        from src.kvm_core.ocr import OCRManager
        mgr = OCRManager()
        status = mgr.get_status()
        if status["available"]:
            print(f"Tesseract OCR is available at: {status['command']}")
            sys.exit(0)
        else:
            print("ERROR: Tesseract OCR is not available on this host.")
            sys.exit(1)

    warnings.filterwarnings("ignore", message="Unverified HTTPS request")
    log_path = configure_logging()
    logging.getLogger("glkvm_mcp").info("Starting comet-kvm MCP server; log=%s", log_path)
    mcp.run()
