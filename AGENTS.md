# AGENTS.md

## Purpose

This repository is `Coldaine/comet-kvm-codex-plugin` — a packaged plugin for GL.iNet Comet KVM-driven hardware triage workflows. It is a selective fork of `kennypeh85/glkvm-mcp` (upstream MCP server). The two projects diverge strongly; see the [Upstream Relationship](README.md#upstream-relationship) section in the README.

Most authority lives in [`docs/NORTH_STAR.md`](docs/NORTH_STAR.md) and [`docs/decisions.md`](docs/decisions.md). This file is the operating-rules summary for agents working in this repo.

## Agent Topology — Read This Before Working in This Repo

This project involves **three distinct agent roles**. Conflating them causes architectural confusion. Know which role you're filling at any given moment.

The same agent instance may fill multiple roles — the developer agent can also act as the driver agent when operating the Comet through MCP tools. The point is not "you are always one of these," it's "use the right instruction surface for the role you're filling right now."

| Role | What it does | Where its instructions live |
|------|-------------|---------------------------|
| **Developer agent** | Writes, tests, refactors the plugin's source code | **This file (AGENTS.md)** + `docs/NORTH_STAR.md` + `docs/decisions.md` |
| **Driver agent** | Operates the Comet KVM at runtime: navigates BIOS, changes settings, collects HWiNFO logs, runs experiments | **The skill files** under `skills/comet-bios-triage/` |
| **VLM agent** | A vision-language model invoked as a service: receives BIOS screenshots, returns structured parses (labels, UI types, values). Does not navigate, does not edit code. | **The VLM prompt/schema contract** (built into the cartographer tool, not yet written) |

When filling the developer role, do not put driver-agent instructions or VLM-agent prompt contracts in AGENTS.md — those belong in the skill files and the cartographer tool respectively. When filling the driver role, follow the skill files, not this file.

## Operating Rules

- Follow `docs/NORTH_STAR.md` as the top-level project authority and `docs/decisions.md` for implementation decisions.
- When working as the developer agent, read the `comet-bios-triage` skill for context, but do not put driver-agent operational rules here.
- **Do not commit credentials.** The only secret is `COMET_PASSWORD`, managed via Doppler (`doppler.yaml`). Host (`192.168.0.126`) and username (`admin`) are non-sensitive and safe in code/config. See `docs/reference/comet-api.md#security-model`.
- Do not commit screenshots, HWiNFO logs, or live state files.
- Use `scripts/comet_preflight.py` for local host checks that do not send KVM actions.
- Use `scripts/run_ledger.py` to create or update experiment records.
- Keep `upstream` pointing at `kennypeh85/glkvm-mcp` (fetch-only, push disabled). Selectively cherry-pick bug fixes or API improvements when relevant — this repo is not a mirror and does not track upstream releases.

## Live Hardware Constraints

- **Target:** Comet KVM (GL-RM1) at `192.168.0.126` on LAN
- **ATX power control:** Not available. The Comet requires the ATX add-on board to physically power cycle the target. Without it, reboots and BIOS entry require manual power-button press. The `/api/atx/*` endpoints exist on the device but are not wrapped in MCP tools yet.
- **BIOS entry workflow (without ATX):** Manually power on the target → agent polls screenshots until POST detected → agent sends BIOS entry key (`Delete`, `F2`, `Escape`, etc.) → agent enters BIOS navigation mode.
- **Credentials:** `doppler run -- uv run glkvm_mcp.py` injects `COMET_PASSWORD`. Run `doppler setup` first if not already configured.
