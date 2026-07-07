# North Star

## Goals

- Package `kennypeh85/glkvm-mcp` as a Codex plugin for GL.iNet Comet KVM workflows.
- Build a BIOS cartography tool that enumerates the complete UI tree of a target board's BIOS, deterministically, using a VLM for per-screen structured perception and a Python DFS driver for navigation.
- Persist BIOS maps as labeled, reusable artifacts so they can be recalled when reconnecting to the same computer or matched against a similar board.
- Run a stateful screen-level position tracker during live BIOS sessions that validates expected transitions against a stored map, without relying on the main LLM to hold screen position.
- Drive MSI Z690 BIOS tuning against stored maps — one setting per run, with visible confirmation before and after every change.
- Validate every BIOS change in Windows via HWiNFO thermal, voltage, power, throttling, and WHEA analysis before continuing.

## Authority Order

1. `docs/NORTHSTAR.md`
2. `skills/comet-bios-triage/SKILL.md`
3. `skills/comet-bios-triage/references/stateful-control-model.md`
4. `docs/reference/comet-hardware.md`
5. `docs/reference/comet-api.md`
6. `docs/plans/comet-kvm-codex-plugin.md`
7. `AGENTS.md`
