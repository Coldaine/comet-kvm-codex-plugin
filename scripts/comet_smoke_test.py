#!/usr/bin/env python
"""
Live smoke test against a Comet KVM (read-only).

Exercises the transport that the MCP server depends on WITHOUT sending any
keystrokes or mutations to the target:

  1. Connect + authenticate (COMET_PASSWORD from env / Doppler)
  2. GET /api/info (sysinfo)
  3. Capture one screenshot (proves the HDMI/video pipeline)

It intentionally does NOT send HID input, since the target may be running an OS
rather than sitting at BIOS. Safe to run against a live machine.

Usage:
    doppler run -- uv run scripts/comet_smoke_test.py
    # or, if COMET_PASSWORD is already exported:
    uv run scripts/comet_smoke_test.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import datetime

# Ensure repo root is importable when run as a script.
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from src.bios_sidecar.comet.client import CometClient  # noqa: E402


async def main() -> int:
    host = os.environ.get("COMET_HOST", "192.168.0.126")
    username = os.environ.get("COMET_USERNAME", "admin")
    password = os.environ.get("COMET_PASSWORD") or os.environ.get("GLCOMET_ADMIN_PASSWORD")

    print(f"[smoke] target host   : {host}")
    print(f"[smoke] username      : {username}")
    if not password:
        print("[smoke] FAIL: COMET_PASSWORD not set. Run via 'doppler run -- ...' "
              "or export COMET_PASSWORD in this shell.")
        return 2

    client = CometClient(host=host, username=username, password=password)

    try:
        print("[smoke] connecting ...")
        await client.connect()
        print(f"[smoke] connected     : {client.is_connected()}")
    except Exception as e:  # noqa: BLE001
        print(f"[smoke] FAIL: connect/auth error: {e}")
        return 3

    exit_code = 0
    try:
        # 1. sysinfo
        try:
            info = await client.get_sysinfo()
            # Print a compact summary rather than the whole payload.
            keys = list(info.keys()) if isinstance(info, dict) else type(info).__name__
            print(f"[smoke] sysinfo OK    : top-level keys = {keys}")
        except Exception as e:  # noqa: BLE001
            print(f"[smoke] WARN: sysinfo failed: {e}")
            exit_code = 1

        # 2. screenshot
        try:
            data = await client.get_screenshot(preview=False)
            out_dir = os.path.join(REPO_ROOT, "state", "screenshots")
            os.makedirs(out_dir, exist_ok=True)
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            out_path = os.path.join(out_dir, f"smoke_{ts}.jpg")
            with open(out_path, "wb") as f:
                f.write(data)
            print(f"[smoke] screenshot OK : {len(data)} bytes -> {out_path}")
        except Exception as e:  # noqa: BLE001
            print(f"[smoke] WARN: screenshot failed: {e}")
            exit_code = 1
    finally:
        await client.disconnect()
        print("[smoke] disconnected")

    print("[smoke] PASS" if exit_code == 0 else "[smoke] COMPLETED WITH WARNINGS")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
