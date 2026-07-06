# Comet KVM Codex Plugin Plan

## Goal

Build a full Codex plugin that gives Codex safe, stateful GL.iNet Comet KVM control for MSI Z690 BIOS tuning and HWiNFO thermal-analysis loops.

## Architecture

Use this fork of `kennypeh85/glkvm-mcp` as the direct Comet control layer. The MCP server provides hands and eyes: connect, screenshot, OCR, keyboard, mouse, and release-all. The Codex skill and run ledger provide workflow state: current phase, planned BIOS change, screenshots, HWiNFO log path, analysis result, and stop/continue decision.

## Stateful Workflow

The allowed phases and transition rules are defined in `skills/comet-bios-triage/references/stateful-control-model.md`.

Each BIOS experiment must record:

- target Comet device,
- planned setting change,
- screenshot before the change,
- screenshot after the change,
- save confirmation screenshot,
- HWiNFO CSV path,
- WHEA/crash/throttle status,
- result and next recommendation.

## Initial Scope

- Package the existing `glkvm_mcp.py` as a Codex plugin MCP server.
- Add a `comet-bios-triage` skill.
- Add non-destructive local preflight tooling.
- Add a run ledger for experiment state.
- Keep runtime screenshots, logs, and state files out of Git by default.

## Deferred Scope

- ATX controls, after Comet ATX wiring and endpoint behavior are verified.
- MSD/ISO mounting, for OS install workflows.
- Multi-target config, after a second KVM target exists.
- Agentic-KVM-style audit/config expansion, after the basic Comet plugin proves useful.

## First Live-Safe Sequence

The first live-safe MCP sequence is defined in `skills/comet-bios-triage/references/stateful-control-model.md` and should remain the single source of truth for smoke-test ordering.
