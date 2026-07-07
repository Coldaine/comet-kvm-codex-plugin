# AGENTS.md

## Purpose

This repository is `Coldaine/comet-kvm-codex-plugin` — a packaged plugin for GL.iNet Comet KVM-driven hardware triage workflows. It is a selective fork of `kennypeh85/glkvm-mcp` (upstream MCP server). The two projects diverge strongly; see the [Upstream Relationship](README.md#upstream-relationship) section in the README.

Most authority lives in [`docs/NORTH_STAR.md`](docs/NORTH_STAR.md) and [`docs/decisions.md`](docs/decisions.md). This file is the operating-rules summary for agents working in this repo.

## Operating Rules

- Follow `docs/NORTH_STAR.md` as the top-level project authority and `docs/decisions.md` for implementation decisions.
- Follow the `comet-bios-triage` skill before operating BIOS or pre-OS workflows.
- Do not commit Comet credentials, screenshots, HWiNFO logs, or live state files.
- Use `scripts/comet_preflight.py` for local host checks that do not send KVM actions.
- Use `scripts/run_ledger.py` to create or update experiment records.
- Do not use blind key sequences for BIOS changes.
- Run `kvm_release_all` after interrupted input or uncertain HID state.
- Keep `upstream` pointing at `kennypeh85/glkvm-mcp` (fetch-only, push disabled). Selectively cherry-pick bug fixes or API improvements when relevant — this repo is not a mirror and does not track upstream releases.
