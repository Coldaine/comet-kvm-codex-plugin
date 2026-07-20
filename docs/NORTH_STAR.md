# North Star

## Why This Exists

Physical machines still need BIOS, pre-OS, and Windows-side triage that ordinary remote-desktop and VM tools cannot reach. This project packages Comet KVM control so an agent can do that work on real hardware.

## Goals

- **G1.** Enable hardware triage on physical machines through GL.iNet Comet KVM — BIOS configuration, pre-OS operations, and Windows-side validation.
- **G2.** Ship a packaged Codex plugin first (MCP server + driver skills), with thin per-tool manifests for other harnesses after Codex is proven.
- **G3.** Separate universal KVM primitives from BIOS-aware workflow so transport stays general and firmware semantics stay optional.
- **G4.** Prefer durable, reusable board knowledge (maps, verified transitions) over relying on the main LLM to hold live screen position.

## Anti-Goals

- **AG1.** Not VM orchestration or hypervisor management.
- **AG2.** Not general-purpose remote desktop for day-to-day interactive use.
- **AG3.** Not a product that depends on device-side OCR as the MCP text engine (host perception only; see `docs/decisions.md` D-K9).

## Where detail lives

| Concern | Home |
|---|---|
| System shape, two layers, cartography spike design | `docs/architecture.md` |
| Implementation choices (OCR path, packaging, map store, …) | `docs/decisions.md` |
| KVM pipeline and tool surface | `docs/kvm-core.md` |
| Live MSI Z690 / disposable-node proof | `docs/workflows/live-hardware-qualification.md` |
| Runtime driver procedure | `skills/comet-kvm-operations/`, `skills/comet-bios-triage/` |
| Doc authority ladder (developer) | `AGENTS.md` |
