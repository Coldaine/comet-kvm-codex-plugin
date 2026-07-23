---
name: comet-kvm-operations
description: >
  Operate or diagnose a physical machine through a GL.iNet Comet or
  GLKVM-compatible KVM. Use when the user wants to connect to a Comet, select a
  target, inspect or read the live console, send keyboard or mouse input,
  control power, wake a machine, attach virtual media, recover or boot a
  physical host, inspect the Comet appliance, or use its Tailscale-accessible
  management path. Do not use for editing this plugin's source code, shopping
  for KVM hardware, researching the Comet API, or general discussion that does
  not require operating a device. For explicit BIOS or UEFI setting inspection,
  mapping, or mutation, also use the specialized comet-bios-triage skill.
---

# Comet KVM Operations

Use this file as a router, not an API catalog. Read only the reference that
matches the current outcome. Read another only when the task crosses domains.

The bundled `comet-kvm` MCP tool schemas are authoritative for exact names,
arguments, capabilities, and returned fields.

## Route the operation

- For connection state, target selection, or initial machine-state discovery,
  read [sessions and targets](references/sessions-and-targets.md).
- For screenshots, OCR, keyboard, mouse, or interrupted input, read
  [console control](references/console-control.md).
- For wake, power, reset, force-off, or recovery, read
  [power and recovery](references/power-and-recovery.md).
- For ISO or image upload, remote fetch, mount, boot, or cleanup, read
  [virtual media](references/virtual-media.md).
- For a visible shell when no exact transport is available, read
  [visible-console commands](references/visible-console.md).
- For Comet capabilities, streaming, recording, metrics, or Tailscale status,
  read [appliance diagnostics](references/appliance-diagnostics.md).
- For firmware inspection, mapping, or mutation, read
  [BIOS handoff](references/bios-handoff.md), then use the specialized
  `comet-bios-triage` skill for the firmware-specific portion.

## Shared operating contract

Resolve the intended target and observe before mutating. Verify the resulting
machine state after input, power, or media actions instead of treating a
successful tool response as proof. After interrupted HID input, call
`kvm_release_all` and re-observe.

Prefer another already-available exact interface such as the Proxmox API or SSH
when it is healthy and provides the required operation. Use KVM for pre-boot,
installer, recovery, network-down, frozen, or otherwise inaccessible states.

Do not reproduce raw GLKVM HTTP requests. The MCP server owns authentication,
wire contracts, retries, streaming, and response normalization. Do not drive the
Comet web UI with browser automation (self-signed cert interstitial). If you
must go raw, use the auth and stream contracts in
[`docs/reference/comet-api.md`](../../docs/reference/comet-api.md) — do not
guess `/api/login`.

## Result

Report the target operated, important initial state, material actions,
verification evidence, current machine state, and any power or media state
intentionally left behind.
