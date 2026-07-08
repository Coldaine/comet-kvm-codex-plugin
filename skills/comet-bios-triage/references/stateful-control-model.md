# Stateful Control Model

The MCP server provides transport (screenshots, keyboard, mouse, OCR). The workflow is stateful at two granularity levels: **workflow phases** (this document) and **screen-level position** (the state engine, per `docs/decisions.md` D7/D8).

## Two Granularity Levels

| Level | What it tracks | Who maintains it | Lifetime | Example question |
|-------|---------------|-----------------|----------|-----------------|
| **Workflow phase** (this doc) | Which stage of an experiment are we in | The agent + run ledger | Across sessions, persisted | "Are we in the bios-edit phase?" |
| **Screen position** (state engine) | Which BIOS menu node are we on right now | The sidecar state tracker in `glkvm_mcp.py` | Ephemeral, per live session | "Are we on the Overclocking submenu row 3?" |

Neither subsumes the other. The phase model governs the experiment lifecycle. The state engine governs live navigation safety within a phase — it validates that each keystroke produced the screen transition the stored map predicted.

## Cartography Prerequisite

Before any `bios-edit` phase, a BIOS map should exist for the target board. Cartography (building the map) is a one-time prerequisite that runs within the `bios-read` phase — it visits every reachable screen, records the UI tree, and persists the map. See `docs/decisions.md` D3 for skill placement and `docs/NORTH_STAR.md` for the cartography spike scope.

If no map exists, the agent should either run cartography first or fall back to live VLM-driven navigation (slower, non-deterministic, and less safe).

## Workflow Phases

- `planned`
- `preflight`
- `bios-entry`
- `bios-read` — includes cartography if no map exists
- `bios-edit`
- `save-confirm`
- `windows-boot`
- `hwinfo-log`
- `analysis`
- `done`
- `blocked`

## Screen-Level State Engine

When a BIOS map is loaded, the state engine (running inside `glkvm_mcp.py` during tool execution) provides:

- **Current screen identification** — matches live screenshots against map nodes via perceptual hash + OCR fingerprint (`kvm_match_screen`).
- **Transition validation** — when keys are sent during path execution, the engine validates the destination edge from the map. If it doesn't match, it halts and triggers VLM grounding.
- **On-Demand VLM Grounding** — calls the VLM tool (`kvm_vlm_parse`) only when entering/syncing, checking options, or verifying post-mutation values to avoid API latency.

The state engine does not replace the workflow phases. It operates *within* a phase (typically `bios-read`, `bios-edit`, and `save-confirm`) to ensure the agent is where it thinks it is before taking an action.

## Action Recording

Every action must record:

- phase before action,
- screen node before action (when a map is loaded),
- screenshot before action when video is available,
- exact MCP action sent,
- screenshot after action when video is available,
- observed OCR text or manual visual note,
- screen node after action (when a map is loaded),
- next phase.

## Transition Rules

Never transition from `bios-edit` to `save-confirm` unless the changed field is visible. Never transition from `save-confirm` to `windows-boot` unless the save confirmation screen is visible.

When the state engine is active, these transitions are additionally gated by screen-node validation — the expected node must match the observed screen before the transition is allowed.

## Safe Tuning MCP Sequence

1. `bios_connect` — establish session.
2. `bios_observe_state` — verify initial position and sync state.
3. `bios_navigate_to` — navigate to OC/CPU configuration nodes.
4. `bios_propose_setting_change` — offline planning and policy evaluation.
5. `bios_apply_setting_change` — apply the approved mutation directly and verify visually via the VLM tool.
6. `bios_save_and_reboot` — execute save, verify dialog, and reboot.
7. `bios_disconnect` — clean up connection.
