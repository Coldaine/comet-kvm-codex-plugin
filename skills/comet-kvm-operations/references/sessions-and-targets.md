# Sessions and Targets

Read this file when the task begins with connection state, target selection, or
initial machine-state discovery.

## Resolve the target

Start with `kvm_status`. Reuse an existing session only when its target
unambiguously matches the requested machine.

When a new session is required, resolve the Comet's network host first, then
call `kvm_connect(host=..., target=...)`. The required `host` identifies the
Comet appliance; `target` is only the stable logical session name for the
attached machine, such as `pve01` or `nas02`. Never substitute the logical
target name for an unknown Comet host.

When multiple sessions exist:

- call `kvm_select_target` before using KVM input tools;
- pass an explicit `target` to Comet-specific tools that accept it;
- never assume the selected target is correct when the request names another
  machine or is ambiguous.

Selected-target tools such as screenshots, OCR, HID input, and `bios_*` do not
take a target in the current schema. Select once, then call them with only their
documented arguments. Use `kvm_disconnect(target=...)` when closing one
completed session so unrelated sessions remain active.

Use the connection capability profile to decide whether ATX, virtual media,
OCR, recording, and other subsystems are available. Call
`comet_capabilities` with refresh only after a firmware, hardware, or
configuration change, or when the cached profile is missing.

## Establish the machine phase

Capture the console and classify the visible state as powered off or no signal,
POST, BIOS or UEFI, bootloader, one-time boot menu, installer, operating system,
recovery shell, crash, boot loop, or unknown. Use OCR only when text materially
improves the classification. Do not send input merely to discover state when a
read-only observation is sufficient.

Reconnect only when `kvm_status` shows the transport is unusable or a bounded
retry confirms transport loss. After reconnecting, recapture the screen instead
of replaying the last input.

Call `kvm_disconnect` for the completed target when no continuing observation
is needed. Preserve other sessions unless the user asked to close them.
