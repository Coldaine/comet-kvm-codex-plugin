# Perception Contract v2 — richer BIOS screen transcription

**Status: Implemented (Phase 1)**
**Date: 2026-07-27**
**Branch: feat/perception-contract-v2**

## Problem

The v1 VLM contract asked for five things: screen title, breadcrumb, cursor row
index, a flat entry list, and a literal six-keyword blocklist flag. Downstream
code already plumbed richer perception — `normalize.py` read per-entry `bbox`
and a parse `confidence` that the prompt never requested, so both were always
fabricated defaults (None and 0.90). Modal dialogs, the footer hotkey legend,
help-pane text, scroll indicators, and grid layouts were invisible to the
pipeline, which is exactly where the crawler's blind spots live (exit prompts,
one-tab-only exploration, EZ-mode grids).

## Design principle (unchanged from v1)

The VLM is a transcriber. It never navigates, never picks keys, never relaxes
policy. Every v2 field is advisory input to the deterministic Python policy
layer, and risk-related fields only ever make the system MORE restrictive: the
literal keyword blocklist remains as a floor and the VLM's semantic risk output
is unioned with it, never substituted for it.

## v2 schema additions (all optional — v1 parses still validate)

| Field | Type | Consumer |
|---|---|---|
| `screen_kind` | StateKind enum string | replaces title-keyword heuristic; heuristic stays as fallback |
| `layout` | `list \| grid \| tabs_with_list \| dialog` | cursor model selection; future tab-navigation frontier |
| `entries[].selected` | bool | grid-safe selection (replaces row-index-only `cursor_at`, which is kept) |
| `entries[].bbox` | `[x0,y0,x1,y1]` px | crop verification; future mouse path |
| `entries[].legible` | bool | low-legibility retry / crop second pass (Phase 3) |
| `help_text` | string | capability index enrichment |
| `hotkeys` | `[{key, action}]` | vendor-true key semantics read off the footer legend |
| `modal` | `{present, title, message, buttons, focused_button}` | modal-aware action policy: Escape-only while a dialog is open |
| `scroll` | `{more_above, more_below}` | evidence-based row-scan termination |
| `risk` | `{dangerous, reason, keywords_seen}` | semantic danger union with keyword blocklist |
| `confidence` | 0..1 | honest parse confidence instead of the fabricated 0.90/0.92 |

## Normalization rules

- `screen_kind`: use the VLM value when it is a valid `StateKind`; otherwise
  fall back to `parse_state_kind(title)`.
- Destructive-screen hazard: computed from the *union* of the chosen
  `screen_kind` and the title heuristic `parse_state_kind(title)`, so a
  wrong-but-valid VLM kind can never suppress a `flash_utility` /
  `secure_erase` / `password_prompt` hazard the title alone would have raised.
- Selection: an entry is selected when its `selected` flag is true OR its index
  equals `cursor_at` (v1 compatibility).
- Risk union: `risk.dangerous` sets `blocklist_flag`, appends `vlm_semantic`
  to hazards, merges `keywords_seen`, and records `reason`. Keyword and
  screen-kind blocklisting behave exactly as v1.
- Modal restriction: while `modal.present`, action policy collapses to
  `safe=["Escape"]` with Enter/F10/F6 blocked — a modal's Enter can confirm a
  save dialog.
- Confidence: the VLM value flows into `selection.confidence` and
  `ConfidenceMetrics.vlm`; defaults apply only when the field is absent.

## Transport upgrades

- **Strict structured outputs**: openai/openrouter requests carry
  `response_format: {type: json_schema, schema: BiosScreenParse.model_json_schema()}`.
  On HTTP 400 the client downgrades to `json_object`, then to no
  `response_format` (ollama/vllm start at `json_object`). The 3-attempt
  validation loop remains as the last line.
- **Locked-in free endpoint**: the openrouter provider default model is
  `openrouter/free` — OpenRouter's Free Models Router ($0; image content in
  the request routes it to vision-capable free models such as Gemma 4 31B).
  Free-tier limits: ~20 requests/minute, ~200/day; `.mcp.json` pins
  `VLM_PROVIDER=openrouter` + `VLM_MODEL=openrouter/free` so a fresh clone
  works with only a key.
- **Doppler key fallback**: when `VLM_API_KEY` is not in the environment, the
  key resolves from the Doppler CLI (secret `OPENROUTER_API_KEY`, project from
  `doppler.yaml`), cached in-process like the Comet password. Free models still
  require an OpenRouter account key.

## Persistence

`BiosState` gains `layout`, `help_text`, `hotkeys`, `scroll`; `ModalMetadata`
gains `title`/`focused`; `ControlEntry` gains `legible`; `RiskStatus` gains
`reason`. The SQLite `states` table stores the new screen-level fields plus the
modal in a single `extras` JSON column, added via an idempotent
`ALTER TABLE` migration so existing map databases keep working.

## Phasing

- **Phase 1 (this change)**: schema, prompt, normalization, transport, config,
  persistence. The mock provider keeps its v1 shape — v2 fields are optional,
  so v1 parses remain valid; tests exercise v2 through normalize directly.
- **Phase 2**: consumers — crawler builds allowed actions from observed
  `hotkeys`, restricts under `modal.present`, and enumerates ArrowLeft/Right
  when `layout=tabs_with_list` (fixes one-tab-only exploration); settler uses
  `confidence`/`legible` to trigger recapture.
- **Phase 3**: native-resolution crop second pass for illegible regions;
  multi-image mutation verification (`verify_change(before, after, expected)`);
  bbox-grounded mouse navigation for Click-BIOS-style UIs under the same
  propose/apply discipline.

Validation of parse quality against real firmware is deliberately deferred to
the planned live-drive session: hand-labeled frames from that session become
the eval set for this prompt across candidate providers.
