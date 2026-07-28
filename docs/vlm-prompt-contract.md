# VLM Prompt Contract (Draft)

> **Repo:** `Coldaine/comet-kvm-codex-plugin` (fork of `kennypeh85/glkvm-mcp`)
> **Status:** Draft — 2026-07-07, amended 2026-07-27 for Perception Contract v2. Sidecar-internal design artifact. This documents the prompt that will be embedded in the BIOS sidecar/cartographer tool's source code as a string constant/template. It is NOT KVM-core architecture. It is NOT a skill file — the VLM does not read markdown from the filesystem. It is NOT reference material — it is a design artifact that justifies every element of the prompt we will send to the VLM API at call time.
>
> **v2 update (2026-07-27):** the schema below is the v1 baseline. Perception Contract v2 adds `screen_kind`, `layout`, per-entry `selected`/`bbox`/`legible`, `help_text`, `hotkeys`, `modal`, `scroll`, a structured `risk` object, and `confidence` — all optional, so v1 parses still validate. See [`docs/superpowers/specs/2026-07-27-perception-contract-v2.md`](superpowers/specs/2026-07-27-perception-contract-v2.md) for the full design and normalization rules; this document is amended in place below rather than forked, since the transcriber-only principle and the v1 fields are unchanged.

## Why This Is a Prompt, Not a Skill

The VLM is not a file-reading agent or peer role. It is a service invoked via an API call: the cartographer tool sends a screenshot image + a prompt string, and the VLM returns a JSON object. The VLM has no filesystem access, no skill-loading mechanism, and no persistent context across calls. Every call is stateless.

The KVM core does not know about this prompt. It exposes screenshots, OCR, HID, and Comet hardware APIs. The BIOS sidecar may call those primitives and then call a VLM to interpret BIOS screenshots.

Therefore, the VLM's instructions must be **embedded in the code that calls it** — the prompt is a string the cartographer tool passes to the VLM API. This document drafts that string and justifies every element in it. When the cartographer tool is implemented, this prompt becomes a code artifact (a string constant or template), not a documentation file.

This is why the prompt does not go in `skills/` — skills are for agents that read markdown at runtime. The VLM doesn't read markdown; it receives a prompt string programmatically.

## Why This Is Not in docs/reference/

`docs/reference/` contains verified facts about external systems (Comet hardware, Comet API). This document is a design artifact about our own choices — the prompt we will send to the VLM and the justification for its contents. It goes in `docs/` alongside `architecture.md` and `decisions.md`.

## The Prompt

### System Prompt

```
You are a BIOS screen parser. You receive a screenshot of a BIOS/UEFI interface and return a structured JSON description of what is on screen.

You do NOT navigate. You do NOT decide what key to press next. You do NOT reason about BIOS settings or their effects. You ONLY describe what is visually present on the screen.

Return ONLY a JSON object matching the schema below. No prose, no explanations, no chain-of-thought, no markdown formatting. Just the JSON object.

If you cannot read a value or identify an element type, use null or "unknown" — do not guess.
```

### Justification of the system prompt

| Element | Why it's there |
|---------|---------------|
| "You are a BIOS screen parser" | Frames the task as perception, not action. Prevents the VLM from drifting into navigation suggestions or BIOS tuning advice. |
| "You do NOT navigate / decide / reason" | Explicitly forbids action selection and reasoning. This is the core architectural boundary — the VLM perceives, the Python driver navigates. See `docs/architecture.md`. |
| "Return ONLY a JSON object" | Enforces the strict schema contract. No prose means no parsing ambiguity. The driver code does `json.loads(response)` directly. |
| "No chain-of-thought" | Chain-of-thought adds latency, output tokens, and non-determinism even at temperature 0. If the VLM supports NOTHINK mode, this is reinforced by the mode. See `docs/architecture.md`. |
| "If you cannot read a value, use null" | Prevents hallucination. A null/unknown value is a gap in the map; a guessed value is a silently wrong map. Gaps are recoverable through targeted re-probes or manual review; wrong values are dangerous because the driver may navigate to a setting that doesn't exist or misread its type. |

### User Prompt (per screenshot)

```
Parse this BIOS screenshot and return the screen description as JSON.

Schema:
{
  "screen_title": string | null,          // The title/header of the current screen, if visible
  "menu_path": string[] | null,           // Breadcrumb path if visible (e.g., ["Settings", "Advanced", "CPU"])
  "cursor_at": number | null,             // 0-indexed row position of the highlighted/cursor entry
  "entries": [
    {
      "label": string,                    // The text label of this menu entry
      "type": "submenu" | "leaf-toggle" | "leaf-numeric" | "leaf-enum" | "leaf-info" | "unknown",
      "value": string | number | null,    // Current value if visible (e.g., "Enabled", 42, "Auto")
      "options": string[] | null,         // Available options for leaf-enum (e.g., ["Mode 1", "Mode 2", "Auto"])
      "key_to_enter": string              // The keystroke that activates this entry (usually "Enter")
    }
  ],
  "blocklist_flag": boolean,              // true if any dangerous keyword is visible on screen
  "blocklist_keywords": string[]          // List of dangerous keywords detected, empty if none
}

Dangerous keywords to flag: "Flash", "Secure Erase", "RAID", "Boot Order", "Password", "Set Password"

Element type definitions:
- submenu: selecting this entry navigates to another screen/menu
- leaf-toggle: a binary setting (Enabled/Disabled, On/Off)
- leaf-numeric: a numeric input field (voltage, frequency, ratio)
- leaf-enum: a dropdown with a fixed set of options
- leaf-info: read-only information (temperatures, CPU model, BIOS version)
- unknown: cannot determine the element type from the screen

Return only the JSON object. No other text.
```

### Justification of the user prompt schema

| Field | Why it's there |
|-------|---------------|
| `screen_title` | Helps the driver identify which screen it's on. Used as a human-readable label in the map and in the Semantic Capability Index. |
| `menu_path` | If the BIOS shows a breadcrumb (some do), this helps validate crawl depth. If no breadcrumb is visible, null — the driver tracks depth via its DFS stack. |
| `cursor_at` | The 0-indexed row the highlight is on. The driver needs this to know which entry is currently selected — it determines whether to send Tab/Down to move to the next entry or Enter to descend. |
| `entries[].label` | The text label of each menu entry. This is the primary key the Semantic Capability Index uses to identify settings. Must be exact — "CPU Lite Load" not "CPULiteLoad". |
| `entries[].type` | The UI element taxonomy. The driver uses this to decide how to interact: submenus get Enter (descend), leaf values get Enter (open edit) then a different interaction pattern depending on type. Fixed enum (`submenu`, `leaf-toggle`, `leaf-numeric`, `leaf-enum`, `leaf-info`, `unknown`) prevents free-form type strings that would break downstream parsing. |
| `entries[].value` | Current value of the setting. For toggles: "Enabled"/"Disabled". For numerics: the number. For enums: the selected option string. For submenus: null. This is what the driver reads to confirm a setting's current state before changing it. |
| `entries[].options` | For leaf-enum only: the list of available options. This lets the Semantic Capability Index record "CPU Lite Load has options Mode 1-4 and Auto" without the driver needing to open the dropdown during a crawl. For other types: null. |
| `entries[].key_to_enter` | The keystroke that activates this entry. Almost always "Enter" in BIOS, but some BIOSes use different keys for different entry types. Making it explicit (rather than hardcoding "Enter" in the driver) handles edge cases without driver changes. |
| `blocklist_flag` | Boolean: did the VLM detect any dangerous keyword on this screen? The driver checks this before sending Enter. If true, the driver backs out (Esc) and marks this zone as blocked in the map. See `docs/architecture.md`. |
| `blocklist_keywords` | Which keywords were detected. Logged for debugging and map annotation. The driver doesn't act differently based on which keyword — any true flag means back out. But knowing which keyword was detected helps a human review the map later. |

### Justification of the dangerous keyword list

| Keyword | Why it's blocklisted |
|---------|---------------------|
| "Flash" | Flash BIOS screen — Enter might start a firmware flash. Irreversible if triggered. |
| "Secure Erase" | Secure Erase screen — Enter might start a drive wipe. Data-destructive. |
| "RAID" | RAID configuration — Enter might change RAID mode, potentially destroying array membership. |
| "Boot Order" | Boot Order changes — Enter might reorder boot devices and require a save/confirm the crawler shouldn't trigger. |
| "Password" | Password/Set Password — Enter might set a BIOS password, locking out future access. Catastrophic if triggered accidentally. |

The list is intentionally small and explicit. It's not "things we don't care about" — it's "things where Enter could trigger an irreversible action." Settings tabs (OC, CPU, DRAM, Advanced) are NOT on the list because Enter navigates or opens an edit dialog, both of which are safe to back out of.

If a keyword appears on a screen that also contains safe settings (e.g., a "Security" tab that has both Password and TPM settings), the driver backs out of the entire screen. The crawler errs on the side of caution — a missing setting in the map is recoverable through targeted follow-up; a triggered destructive action is not.

## v2 Schema Additions (2026-07-27)

The v1 schema above is unchanged and still validates on its own — every v2
field is optional. v2 was added because downstream code (`normalize.py`) was
already reading fields the v1 prompt never asked for (`entries[].bbox`, a
parse `confidence`), so those values were silently fabricated. v2 closes that
gap and gives the VLM a way to describe modal dialogs, footer hotkey legends,
help-pane text, scroll position, and grid layouts, none of which v1 could
express.

| Field | Type | Why it's there |
|---|---|---|
| `screen_kind` | `StateKind` enum string | Replaces the title-keyword heuristic for classifying the screen; the heuristic (`parse_state_kind(title)`) remains as a fallback when this is absent or invalid. |
| `layout` | `"list" \| "grid" \| "tabs_with_list" \| "dialog"` | Tells the driver which cursor model applies (a grid's "selected" concept differs from a list's row index) and, in Phase 2, drives tab-navigation frontier expansion. |
| `entries[].selected` | boolean | Grid-safe selection flag. An entry counts as selected when `selected` is true OR its index equals `cursor_at` (v1 compatibility) — grids can have a highlighted cell that isn't row 0..N of a flat list. |
| `entries[].bbox` | `[x0, y0, x1, y1]` px | Pixel bounding box of the entry, for crop verification now and bbox-grounded mouse navigation later (Phase 3). |
| `entries[].legible` | boolean | Lets the VLM flag a low-confidence read per entry, distinct from overall `confidence`, so the driver can target a crop/retry at just that region (Phase 3). |
| `help_text` | string | Free text from a help pane/footer description, if visible. Feeds the Semantic Capability Index. |
| `hotkeys` | `[{key, action}]` | The footer hotkey legend, transcribed verbatim (e.g. `F10: Save`, `Esc: Exit`). This gives the driver vendor-true key semantics instead of assuming standard AMI/Insyde bindings. |
| `modal` | `{present, title, message, buttons, focused_button}` | Describes an open dialog. When `modal.present` is true, action policy collapses to `safe=["Escape"]` — Enter/F10/F6 are blocked, because a modal's Enter can confirm a save or a destructive action. |
| `scroll` | `{more_above, more_below}` | Lets the driver know whether the visible entry list is a partial view of a longer menu, replacing a guess with evidence for when to stop row-scanning. |
| `risk.dangerous`, `risk.reason`, `risk.keywords_seen` | boolean, string, string[] | Semantic risk assessment. This is unioned with — never a replacement for — the literal keyword blocklist above: `risk.dangerous` sets `blocklist_flag`, appends `vlm_semantic` to hazards, and merges `keywords_seen` into the blocklist keywords. The literal list remains the floor. |
| `confidence` | 0.0–1.0 | Honest parse confidence, replacing the fabricated 0.90/0.92 defaults `normalize.py` used before this field existed. Flows into `selection.confidence` and `ConfidenceMetrics.vlm`; the old defaults apply only when the VLM omits this field. |

The design principle from the top of this document is unchanged: the VLM is
still a pure transcriber. None of the v2 fields let it navigate, pick a key,
or relax policy — `risk` in particular only ever makes the system *more*
restrictive, never less. Full field-by-field normalization rules live in the
spec: [`docs/superpowers/specs/2026-07-27-perception-contract-v2.md`](superpowers/specs/2026-07-27-perception-contract-v2.md).

## Calling Convention

### Parameters

| Parameter | Value | Justification |
|-----------|-------|---------------|
| `temperature` | 0 | Reproducibility. Two parses of the same screenshot must produce identical JSON. See `docs/architecture.md`. |
| `max_tokens` | 2048 | BIOS screens have at most ~20-30 entries. The JSON schema is compact. 2048 tokens is generous headroom while preventing runaway output. |
| `response_format` | JSON (if the API supports it) | Some VLM APIs (OpenAI, vLLM with guided decoding) support forced JSON output mode. Use it if available — it guarantees valid JSON. |
| `NOTHINK mode` | Enabled (if available) | Skips chain-of-thought for faster, more consistent structured output. See `docs/architecture.md`. |

**v2 transport update:** for the `openai` and `openrouter` providers, `response_format`
is no longer best-effort JSON mode — the client sends strict structured
outputs, `{"type": "json_schema", "json_schema": {"strict": true, "schema":
BiosScreenParse.model_json_schema()}}`, so the endpoint enforces the v2 schema
itself. If the endpoint responds `HTTP 400` (schema not supported), the client
downgrades one step to `{"type": "json_object"}`, and on a second 400 drops
`response_format` entirely and relies on the prompt text alone. `ollama`/`vllm`
start directly at `json_object` — they don't advertise strict schema support.
The 3-attempt corrective-retry loop described below is unchanged and remains
the last line of defense regardless of which rung of the ladder succeeded.

### Retry behavior

If the VLM returns malformed JSON or missing required fields:

1. **First retry:** Re-send with a corrective prompt: "Your previous response was not valid JSON or was missing required fields. Return only the JSON object matching the schema."
2. **Second retry:** Re-send with the original prompt (fresh attempt).
3. **After two failures:** Log the screen as `unparseable`, record the screenshot path for manual review, and continue the crawl. The map has a gap at this node, but the crawl doesn't abort.

This ensures a single unparseable screen doesn't block the entire crawl. Gaps are recoverable — the driver agent can re-probe specific screens later with a targeted crawl or manual review flow.

## Open Questions (Not Yet Resolved)

1. **Which VLM?** **Resolved.** Provider routing lives in [`src/bios_sidecar/perception/vlm_client.py`](../src/bios_sidecar/perception/vlm_client.py) (`codex` / `aperture` / `openrouter` / `ollama` / `vllm` / `openai`). Configure via `VLM_PROVIDER`, `VLM_MODEL`, `VLM_BASE_URL`, and `VLM_API_KEY` — see the env var table in [`docs/reference/comet-api.md`](reference/comet-api.md#environment-variables). Missing credentials or unsupported providers fail closed; no fabricated parse is returned.
   **v2 update (2026-07-27):** `.mcp.json` pinned the `openrouter` provider's
   default model to `openrouter/free` — OpenRouter's Free Models Router, $0,
   which auto-selects a vision-capable free model whenever the request
   contains an image (~20 requests/minute, ~200/day free-tier limits). A real
   OpenRouter account key is still required even for free models. When
   `VLM_API_KEY` is unset in the environment, the client now falls back to the
   Doppler CLI secret `OPENROUTER_API_KEY` (project/config from
   `doppler.yaml`), cached in-process for the life of the run the same way the
   Comet admin password is.
   **v3 update (2026-07-28):** live testing showed the Free Models Router is a
   latency/quality lottery (good picks parse in ~3 s; both free `gemma-4`
   variants take 100 s+ and emit schema-violating output that burns all three
   validation retries). `.mcp.json` now defaults to `VLM_PROVIDER=codex`: the
   client shells out to the local Codex CLI as a tiny scripted sub-agent
   (`codex exec --ephemeral -s read-only --output-schema … -i <frame>`, prompt
   via stdin), so parses ride the user's ChatGPT subscription with the model
   and reasoning effort from `~/.codex/config.toml` — measured 20.7 s for a
   complete, correct 10-entry parse of a live Click BIOS 5 screen, no API key.
   The `aperture` provider (tailnet Aperture gateway, tailnet-identity auth,
   default `gemini-oai/gemini-3.5-flash`) is the keyless HTTP alternative and
   the landing zone for additional vision models added to the gateway.
2. **Few-shot examples?** The current prompt is zero-shot. Adding 2-3 BIOS screenshot → JSON examples might improve parse accuracy on the first crawl. Not yet decided.
3. **Image resolution?** The Comet can capture at various resolutions/qualities. What resolution does the VLM need for reliable parsing? Not yet tested.
4. **OCR hint?** Should the VLM receive Tesseract OCR output alongside the image as a robustness hint? OCR is already available via `kvm_ocr_screenshot`. Not yet decided.

Questions 2–4 are still open for implementation tuning. The prompt schema and justification remain stable regardless of provider.
