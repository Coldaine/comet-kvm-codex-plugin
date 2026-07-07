---
name: comet-bios-triage
description: Use when operating a GL.iNet Comet/GLKVM through MCP for BIOS or pre-OS workflows, especially MSI Z690 CPU power/voltage tuning followed by Windows HWiNFO logging and analysis. Triggers include Comet KVM, GLKVM, BIOS driving, UEFI navigation, CPU Lite Load, MSI Z690, HWiNFO thermal triage, and KVM-assisted undervolt testing.
---

# Comet BIOS Triage

Use the Comet MCP tools as hands and eyes, not as a blind macro engine.

Before changing BIOS settings, read:

- `../../docs/architecture.md` — current BIOS cartography and state-engine design
- `../../docs/vlm-prompt-contract.md` — current VLM perception contract
- `references/stateful-control-model.md`
- `references/msi-z690-bios-workflow.md`
- `references/hwinfo-run-loop.md`

`references/bios-cartography.md` is retained only as a superseded historical draft; do not use it as current operating guidance.

Rules:

- Never use blind key sequences for BIOS changes.
- Always capture a screenshot before and after each setting change.
- Change exactly one BIOS variable per run.
- Confirm the visible old value and new value before saving.
- Run `kvm_release_all` after any failed or interrupted input sequence.
- Do not continue after WHEA errors, crashes, score collapse, severe throttling, or clock-stretching.
- Use the run ledger for every experiment.
