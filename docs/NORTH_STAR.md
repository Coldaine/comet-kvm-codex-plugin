# North Star

## Goals

**Overall:** Convert `kennypeh85/glkvm-mcp` into a packaged plugin for GL.iNet Comet KVM-driven hardware triage workflows — BIOS configuration, pre-OS operations, and Windows-side validation on physical machines. Not VM orchestration or general-purpose remote desktop.

**One spike, two layers:** One integrated spike with two layers maturing in parallel: the universal KVM MCP server (transport, OCR, plugin packaging) and the BIOS sidecar (cartography, navigation, mutation). The live-hardware proof point on MSI Z690 is **Planned** — code exists but has not yet been validated end-to-end against a real board.

**Primary target: Codex.** Ship as a Codex plugin first. Skills follow the open `SKILL.md` (agentskills.io) standard and the MCP server is tool-agnostic, so cross-tool compatibility with Claude Code, Cursor, VS Code/Copilot, and others should follow by adding thin per-tool manifests after the Codex plugin is proven.

**First spike — BIOS cartography:**

- Build a tool that near-exhaustively enumerates the UI tree of a target board's BIOS — a Python DFS driver for navigation, a VLM for per-screen structured perception, cycle detection via perceptual hashing. Blocklisted zones (Flash, Secure Erase, RAID, Boot Order, Password) are off-limits to the crawler; everything else is visited.
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
3. `docs/architecture.md`
4. `docs/vlm-prompt-contract.md`
5. `skills/comet-bios-triage/SKILL.md`
6. `skills/comet-bios-triage/references/stateful-control-model.md`
7. `docs/reference/comet-hardware.md`
8. `docs/reference/comet-api.md`
9. `AGENTS.md`
