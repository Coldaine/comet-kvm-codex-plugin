#!/usr/bin/env python
"""
Live smoke test against a Comet KVM (read-only).

Exercises the transport that the MCP server depends on WITHOUT sending any
keystrokes or mutations to the target:

  1. Connect + authenticate (COMET_PASSWORD from Doppler CLI)
  2. GET /api/info (sysinfo)
  3. Capture one screenshot (proves the HDMI/video pipeline)

It intentionally does NOT send HID input, since the target may be running an OS
rather than sitting at BIOS. Safe to run against a live machine.

Usage:
    uv run scripts/comet_smoke_test.py

Requires Doppler CLI authenticated to secrets_managment/dev (see doppler.yaml).
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

from src.kvm_core.comet.client import CometClient  # noqa: E402
from src.kvm_core.doppler_credentials import DopplerAuthError, resolve_comet_password  # noqa: E402


async def main() -> int:
    host = os.environ.get("COMET_HOST", "192.168.0.126")
    username = os.environ.get("COMET_USERNAME", "admin")

    print(f"[smoke] target host   : {host}")
    print(f"[smoke] username      : {username}")
    try:
        password = resolve_comet_password(require=True)
    except DopplerAuthError as exc:
        print(f"[smoke] FAIL: {exc}")
        return 2
    print("[smoke] password      : from Doppler CLI")

    client = CometClient(host=host, username=username, password=password)

    try:
        print("[smoke] connecting ...")
        ok = await client.connect()
        if not ok:
            print("[smoke] FAIL: connect() returned False")
            return 1
        print("[smoke] connected")

        print("[smoke] GET /api/info ...")
        info = await client.get_sysinfo()
        print(f"[smoke] sysinfo keys  : {sorted(info.keys()) if isinstance(info, dict) else type(info)}")

        print("[smoke] snapshot ...")
        frame = await client.get_screenshot(preview=True, max_width=640, quality=50)
        ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        out = os.path.join(REPO_ROOT, "state", "screenshots", f"smoke-{ts}.jpg")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "wb") as fh:
            fh.write(frame)
        print(f"[smoke] screenshot    : {out} ({len(frame)} bytes)")
        print("[smoke] PASS")
        return 0
    except Exception as exc:
        print(f"[smoke] FAIL: {type(exc).__name__}: {exc}")
        return 1
    finally:
        await client.disconnect()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
