# North Star

## Goals

**Overall:** Convert `kennypeh85/glkvm-mcp` into a packaged plugin for GL.iNet Comet KVM-driven hardware triage workflows — BIOS configuration, pre-OS operations, and Windows-side validation on physical machines. Not VM orchestration or general-purpose remote desktop. Target Codex as the first consumer, but design for portability across AI coding tools (Codex, Claude Code, Cursor, etc.) where their plugin/extension architectures permit.

**First spike — BIOS cartography:**

- Build a tool that enumerates the complete UI tree of a target board's BIOS deterministically — a Python DFS driver for navigation, a VLM for per-screen structured perception, cycle detection via perceptual hashing.
- Persist BIOS maps as labeled, reusable artifacts (board model, BIOS version, date) so they can be recalled when reconnecting to the same computer or matched against a similar board.
- Run a stateful screen-level position tracker during live BIOS sessions that validates expected transitions against a stored map, without relying on the main LLM to hold screen position.

**Immediate concrete workflow — MSI Z690 tuning:**

- Drive MSI Z690 BIOS tuning against stored maps — one setting per run, with visible confirmation before and after every change.
- Validate every BIOS change in Windows via HWiNFO thermal, voltage, power, throttling, and WHEA analysis before continuing.

**Future extensions** (after the first spike proves the pattern):

- Additional Comet capabilities and workflows as the plugin matures. The cartography → tune → validate pattern is the template, not the ceiling.

## Authority Order

1. `docs/NORTHSTAR.md`
2. `skills/comet-bios-triage/SKILL.md`
3. `skills/comet-bios-triage/references/stateful-control-model.md`
4. `docs/reference/comet-hardware.md`
5. `docs/reference/comet-api.md`
6. `docs/plans/comet-kvm-codex-plugin.md`
7. `AGENTS.md`
