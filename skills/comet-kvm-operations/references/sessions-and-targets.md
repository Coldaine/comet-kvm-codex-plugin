# Sessions and Targets

Read this file when the task begins with connection state, target selection, or
initial machine-state discovery.

## Resolve the target

Start with `kvm_status`. Reuse an existing session only when its target
unambiguously matches the requested machine.

When a new session is required, call `kvm_connect` with a stable `target` name
that identifies the physical host, such as `pve01` or `nas02`, rather than
accumulating anonymous default sessions.

When multiple sessions exist:

- call `kvm_select_target` before using KVM input tools;
- pass an explicit `target` to Comet-specific tools that accept it;
- never assume the selected target is correct when the request names another
  machine or is ambiguous.

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
