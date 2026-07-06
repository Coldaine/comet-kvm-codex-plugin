# AGENTS.md

## Purpose

This repository is a Codex plugin fork of `kennypeh85/glkvm-mcp` for GL.iNet Comet KVM control and MSI Z690 BIOS/HWiNFO triage workflows.

## Operating Rules

- Treat `glkvm_mcp.py` as the active MCP server until the code is intentionally split.
- Treat `docs/NORTHSTAR.md` as the top-level project authority.
- Treat `skills/comet-bios-triage/references/stateful-control-model.md` as the canonical workflow phase model.
- Do not commit Comet credentials, screenshots, HWiNFO logs, or live state files.
- Use `scripts\comet_preflight.py` for local host checks that do not send KVM actions.
- Use `scripts\run_ledger.py` to create or update experiment records.
- Use the `comet-bios-triage` skill before operating BIOS or pre-OS workflows.
- Do not use blind key sequences for BIOS changes.
- Run `kvm_release_all` after interrupted input or uncertain HID state.
- Keep `upstream` pointing at `kennypeh85/glkvm-mcp` for manual review of upstream updates.
