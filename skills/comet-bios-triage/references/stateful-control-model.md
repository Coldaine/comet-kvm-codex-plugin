# Stateful Control Model

The MCP server is stateless transport. The workflow is stateful.

Allowed phases:

- `planned`
- `preflight`
- `bios-entry`
- `bios-read`
- `bios-edit`
- `save-confirm`
- `windows-boot`
- `hwinfo-log`
- `analysis`
- `done`
- `blocked`

Every action must record:

- phase before action,
- screenshot before action when video is available,
- exact MCP action sent,
- screenshot after action when video is available,
- observed OCR text or manual visual note,
- next phase.

Never transition from `bios-edit` to `save-confirm` unless the changed field is visible. Never transition from `save-confirm` to `windows-boot` unless the save confirmation screen is visible.

## First Live-Safe MCP Sequence

Use only after credentials are supplied through the chosen MCP client configuration.

1. `kvm_connect`
2. `kvm_status`
3. `kvm_screenshot`
4. `kvm_ocr_screenshot`
5. `kvm_release_all`
6. `kvm_disconnect`

This sequence does not intentionally send target-changing input. If the screenshot is blank, fix video/EDID/cabling before any BIOS workflow.
