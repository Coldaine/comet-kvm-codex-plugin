---
name: comet-bios-triage
description: >
  Inspect, map, change, verify, and save BIOS or UEFI settings through a
  GL.iNet Comet or GLKVM-compatible KVM. Use when the intended outcome is
  firmware configuration, BIOS menu cartography, setting validation,
  save-and-reboot behavior, or explicit MSI CPU power, voltage, Lite Load,
  LLC, CEP, or HWiNFO-backed firmware tuning. Do not use for ordinary console
  viewing, OCR, power control, Wake-on-LAN, virtual media, installer booting,
  operating-system recovery, Proxmox administration, or generic pre-boot
  interaction.
---

# Comet BIOS Triage

Use semantic `bios_*` tools as the firmware control layer. Use the
`comet-kvm-operations` skill for target selection, generic screenshots, raw
keyboard or mouse input, power, media, boot observation, and recovery outside
firmware semantics.

Read only the reference that matches the requested firmware outcome:

- For BIOS observation, cartography, navigation, mutation, save, or recovery,
  read [stateful control](references/stateful-control-model.md).
- For explicit MSI Z690 power, voltage, Lite Load, LLC, or CEP work, also read
  [MSI Z690 workflow](references/msi-z690-bios-workflow.md).
- For an explicitly requested HWiNFO-backed experiment, also read
  [HWiNFO run loop](references/hwinfo-run-loop.md).

Do not preload board-specific or workload-specific references for unrelated
BIOS work. The MCP tool schemas are authoritative for exact arguments and
returned fields.

## Firmware operating contract

1. Resolve the intended target and call `bios_observe_state` before planning a
   firmware action.
2. Use `bios_propose_setting_change` before `bios_apply_setting_change`.
3. Change one firmware variable per experiment. Confirm the visible old value
   and verified new value before saving.
4. Call `bios_save_and_reboot` only when saving is part of the requested
   outcome, then observe the reboot and resulting firmware or operating-system
   state.
5. After failed or interrupted input, call `kvm_release_all`, re-observe, and
   continue from the actual state rather than replaying a blind key sequence.

Never rely on an approval-token or hidden policy engine; this server does not
provide one. Stop after WHEA errors, crashes, performance collapse, severe
throttling, clock-stretching, unexpected firmware state, or unverified input.

## Result

Report the target, initial firmware state, setting changed, visible old and new
values, save decision, reboot verification, and any instability or ambiguity.
