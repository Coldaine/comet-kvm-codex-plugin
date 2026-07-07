# North Star

## Goals

**Overall:** Convert `kennypeh85/glkvm-mcp` into a packaged plugin for GL.iNet Comet KVM-driven hardware triage workflows — BIOS configuration, pre-OS operations, and Windows-side validation on physical machines. Not VM orchestration or general-purpose remote desktop.

**Primary target: Codex.** Ship as a Codex plugin first. Skills follow the open `SKILL.md` (agentskills.io) standard and the MCP server is tool-agnostic, so cross-tool compatibility with Claude Code, Cursor, VS Code/Copilot, and others should follow by adding thin per-tool manifests — but that is deferred until the Codex plugin is proven.

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

1. `docs/NORTH_STAR.md`
2. `docs/decisions.md`
3. `skills/comet-bios-triage/SKILL.md`
4. `skills/comet-bios-triage/references/stateful-control-model.md`
5. `docs/reference/comet-hardware.md`
6. `docs/reference/comet-api.md`
7. `AGENTS.md`
