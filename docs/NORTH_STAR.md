# North Star

## Why This Exists

Physical machines need console and recovery access when ordinary remote desktop,
SSH, and VM tools are unavailable. This project packages GL.iNet Comet KVM
control so an agent can operate that physical boundary without turning the
plugin into a hypervisor manager or a general desktop tool.

## Goals

- **G1.** Make the universal Comet path useful: connect, inspect the console,
  send HID, use virtual media, use available power/WOL controls, and diagnose
  the appliance without exposing it publicly.
- **G2.** Ship that capability as a Codex plugin first (MCP server plus driver
  skills), then add thin manifests for other harnesses when Codex is proven.
- **G3.** Keep universal KVM transport independent of firmware semantics so it
  remains useful for POST, recovery, installers, network-down hosts, and
  ordinary out-of-band work.
- **G4.** Offer BIOS cartography and tuning as a specialist lane for a specific
  firmware task, never as a prerequisite for ordinary Comet operation.

## Anti-Goals

- **AG1.** Not VM orchestration or hypervisor management.
- **AG2.** Not general-purpose remote desktop for day-to-day interactive use.
- **AG3.** Not a product that depends on device-side OCR as the MCP text engine (host perception only; see `docs/decisions.md` D-K9).
- **AG4.** Core operations do not depend on BIOS cartography, board tuning, or
  HWiNFO validation.

## Product lanes

| Lane | Purpose | Current posture |
|---|---|---|
| **Core Comet operations** | Console, HID, screenshots/OCR, appliance diagnostics, virtual media, WOL/power where physically available, and private remote access. | Primary product path and default driver route. |
| **Firmware specialist** | BIOS observation, cartography, setting changes, and optional HWiNFO-backed validation for a named board/workload. | Available only when explicitly requested; its own qualification work does not block the core lane. |

## Where detail lives

| Concern | Home |
|---|---|
| System shape and the boundary between core and specialist lanes | `docs/architecture.md` |
| Implementation choices (OCR path, packaging, map store, …) | `docs/decisions.md` |
| KVM pipeline and tool surface | `docs/kvm-core.md` |
| Core and specialist hardware qualification | `docs/workflows/live-hardware-qualification.md` |
| Ordinary driver procedure | `skills/comet-kvm-operations/` |
| Firmware-only driver procedure | `skills/comet-bios-triage/` |
| Doc authority ladder (developer) | `AGENTS.md` |
