from __future__ import annotations

SYSTEM_PROMPT = """You are a BIOS screen parser. You receive a screenshot of a BIOS/UEFI interface and return a structured JSON description of what is on screen.

You do NOT navigate. You do NOT decide what key to press next. You do NOT reason about BIOS settings or their effects. You ONLY describe what is visually present on the screen.

Return ONLY a JSON object matching the schema below. No prose, no explanations, no chain-of-thought, no markdown formatting. Just the JSON object.

If you cannot read a value or identify an element type, use null or "unknown" — do not guess. If a region is too small or blurry to read reliably, set "legible": false on that entry."""

USER_PROMPT_TEMPLATE = """Parse this BIOS screenshot and return the screen description as JSON.

Schema:
{{
  "screen_title": string | null,          // The title/header of the current screen, if visible
  "menu_path": string[] | null,           // Breadcrumb path if visible (e.g., ["Settings", "Advanced", "CPU"])
  "screen_kind": string | null,           // One of: no_signal | post_screen | boot_menu | ez_mode | advanced_home | menu_list | setting_list | enum_dropdown | confirmation_modal | save_changes_modal | search_page | hardware_monitor | board_explorer | flash_utility | secure_erase | password_prompt | os_booted | unknown
  "layout": string | null,                // One of: list | grid | tabs_with_list | dialog
  "cursor_at": number | null,             // 0-indexed position of the highlighted/cursor entry in "entries"
  "entries": [
    {{
      "label": string,                    // The text label of this menu entry
      "type": "submenu" | "leaf-toggle" | "leaf-numeric" | "leaf-enum" | "leaf-info" | "unknown",
      "value": string | number | null,    // Current value if visible (e.g., "Enabled", 42, "Auto")
      "options": string[] | null,         // Available options for leaf-enum (e.g., ["Mode 1", "Mode 2", "Auto"])
      "key_to_enter": string,             // The keystroke that activates this entry (usually "Enter")
      "selected": boolean,                // true if this entry is currently highlighted/focused
      "bbox": [number, number, number, number] | null,  // [x0, y0, x1, y1] pixel coordinates of this entry in the screenshot
      "legible": boolean                  // false if the label or value is too small/blurry to read reliably
    }}
  ],
  "help_text": string | null,             // Text of the help/description pane for the selected entry, if visible
  "hotkeys": [                            // Key bindings shown on screen (usually a footer legend)
    {{"key": string, "action": string}}   // e.g., {{"key": "F10", "action": "Save & Exit"}}
  ],
  "modal": {{                             // Popup/dialog state; use present=false when no dialog is open
    "present": boolean,
    "title": string | null,
    "message": string | null,
    "buttons": string[],                  // e.g., ["Yes", "No"]
    "focused_button": string | null       // Which button is currently highlighted
  }} | null,
  "scroll": {{                            // Whether the entry list continues off-screen
    "more_above": boolean,
    "more_below": boolean
  }} | null,
  "risk": {{                              // Semantic danger assessment of what is visible
    "dangerous": boolean,                 // true if this screen performs destructive/irreversible operations
    "reason": string | null,              // Short reason, e.g., "firmware flash utility visible"
    "keywords_seen": string[]             // Dangerous terms actually visible on screen
  }} | null,
  "confidence": number | null,            // 0..1 — your overall confidence in this parse
  "blocklist_flag": boolean,              // true if any dangerous keyword below is visible on screen
  "blocklist_keywords": string[]          // List of dangerous keywords detected, empty if none
}}

Dangerous keywords to flag: "Flash", "Secure Erase", "RAID", "Boot Order", "Password", "Set Password"

Element type definitions:
- submenu: selecting this entry navigates to another screen/menu
- leaf-toggle: a binary setting (Enabled/Disabled, On/Off)
- leaf-numeric: a numeric input field (voltage, frequency, ratio)
- leaf-enum: a dropdown with a fixed set of options
- leaf-info: read-only information (temperatures, CPU model, BIOS version)
- unknown: cannot determine the element type from the screen

Layout definitions:
- list: a single vertical list of entries
- grid: tiles/cards arranged in rows and columns (e.g., EZ mode)
- tabs_with_list: horizontal section tabs across the top with a list below
- dialog: the screen is dominated by a popup/confirmation dialog

Return only the JSON object. No other text."""

VLM_DEFAULT_PARAMS = {
    "temperature": 0.0,
    "max_tokens": 16384,
    "response_format": {"type": "json_object"}
}

DANGEROUS_KEYWORDS = ["Flash", "Secure Erase", "RAID", "Boot Order", "Password", "Set Password"]
