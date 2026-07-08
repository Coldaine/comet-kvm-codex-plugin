# AGENTS.md

## Purpose

This repository is `Coldaine/comet-kvm-codex-plugin` — a packaged plugin for GL.iNet Comet KVM-driven hardware triage workflows. It is a selective fork of `kennypeh85/glkvm-mcp` (upstream MCP server). The two projects diverge strongly; see the [Upstream Relationship](README.md#upstream-relationship) section in the README.

Most authority lives in [`docs/NORTH_STAR.md`](docs/NORTH_STAR.md) and [`docs/decisions.md`](docs/decisions.md). KVM-core architecture lives in [`docs/kvm-core.md`](docs/kvm-core.md). This file is the operating-rules summary for agents working in this repo.

## Agent Topology — Read This Before Working in This Repo

This project involves **two agent roles** plus sidecar-called perception services. Conflating them causes architectural confusion. Know which role you're filling at any given moment.

The same agent instance may fill multiple roles — the developer agent can also act as the driver agent when operating the Comet through MCP tools. The point is not "you are always one of these," it's "use the right instruction surface for the role you're filling right now."

| Role | What it does | Where its instructions live |
|------|-------------|---------------------------|
| **Developer agent** | Writes, tests, refactors the plugin's source code | **This file (AGENTS.md)** + `docs/NORTH_STAR.md` + `docs/decisions.md` |
| **Driver agent** | Operates the Comet KVM at runtime: navigates BIOS, changes settings, collects HWiNFO logs, runs experiments | **The skill files** under `skills/comet-bios-triage/` |

The VLM is not a peer agent role. It is a stateless perception service the BIOS sidecar may call with screenshots to get structured parses. It does not navigate, edit code, or read repo docs at runtime.

When filling the developer role, do not put driver-agent instructions or VLM prompt contracts in AGENTS.md — those belong in the skill files and the sidecar prompt/schema implementation respectively. When filling the driver role, follow the skill files, not this file.

## Operating Rules

- Follow `docs/NORTH_STAR.md` as the top-level project authority and `docs/decisions.md` for implementation decisions.
- Follow `docs/kvm-core.md` for the universal KVM MCP server architecture and the KVM/BIOS sidecar boundary.
- When working as the developer agent, read the `comet-bios-triage` skill for context, but do not put driver-agent operational rules here.
- **Do not commit credentials.** The only secret is `COMET_PASSWORD`, managed via Doppler (`doppler.yaml`). Host (`192.168.0.126`) and username (`admin`) are non-sensitive and safe in code/config. See `docs/reference/comet-api.md#security-model`.
- Do not commit screenshots, HWiNFO logs, or live state files.
- Use `scripts/comet_preflight.py` for local host checks that do not send KVM actions.
- Use `scripts/run_ledger.py` to create or update experiment records.
- Keep `upstream` pointing at `kennypeh85/glkvm-mcp` (fetch-only, push disabled). Selectively cherry-pick bug fixes or API improvements when relevant — this repo is not a mirror and does not track upstream releases.

## Live Hardware Constraints

- **Target:** Comet KVM (GL-RM1) at `192.168.0.126` on LAN
- **ATX power control:** Wrapped by `comet_atx_power` and `comet_atx_click`. These tools require the ATX add-on board to be physically installed and wired to the target.
- **BIOS entry workflow:** Use ATX reset/power tools when the add-on board is installed; otherwise manually power on the target. The agent polls screenshots until POST is detected, sends the BIOS entry key (`Delete`, `F2`, `Escape`, etc.), then enters BIOS navigation mode.
- **Credentials:** The only secret is `COMET_PASSWORD`, managed via Doppler (`doppler.yaml`). Host (`192.168.0.126`) and username (`admin`) are non-sensitive and safe in code/config. See `docs/reference/comet-api.md#security-model`.
