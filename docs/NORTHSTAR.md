# North Star

## Purpose

This fork packages `kennypeh85/glkvm-mcp` as a Codex plugin for GL.iNet Comet KVM workflows, with the first concrete path focused on MSI Z690 BIOS tuning and Windows HWiNFO validation.

## Decisions

- `glkvm_mcp.py` remains the active transport until a split is justified.
- The Codex skill owns the human-facing workflow and safety rules.
- `skills/comet-bios-triage/references/stateful-control-model.md` is the canonical phase model.
- `scripts/comet_preflight.py` must stay local-only and must not send live KVM actions.
- Runtime screenshots, logs, device state, and credentials are intentionally ignored by Git.
- Every BIOS-setting experiment needs enough evidence to reconstruct the setting, visible confirmation, Windows boot, and HWiNFO result.

## Authority Order

1. `docs/NORTHSTAR.md`
2. `skills/comet-bios-triage/SKILL.md`
3. `skills/comet-bios-triage/references/stateful-control-model.md`
4. `docs/plans/comet-kvm-codex-plugin.md`
5. `AGENTS.md`
