from __future__ import annotations

SYSTEM_PROMPT = """You are a BIOS screen parser. You receive a screenshot of a BIOS/UEFI interface and return a structured JSON description of what is on screen.

You do NOT navigate. You do NOT decide what key to press next. You do NOT reason about BIOS settings or their effects. You ONLY describe what is visually present on the screen.

Return ONLY a JSON object matching the schema below. No prose, no explanations, no chain-of-thought, no markdown formatting. Just the JSON object.

If you cannot read a value or identify an element type, use null or "unknown" — do not guess."""

USER_PROMPT_TEMPLATE = """Parse this BIOS screenshot and return the screen description as JSON.

Schema:
{{
  "screen_title": string | null,          // The title/header of the current screen, if visible
  "menu_path": string[] | null,           // Breadcrumb path if visible (e.g., ["Settings", "Advanced", "CPU"])
  "cursor_at": number | null,             // 0-indexed row position of the highlighted/cursor entry
  "entries": [
    {{
      "label": string,                    // The text label of this menu entry
      "type": "submenu" | "leaf-toggle" | "leaf-numeric" | "leaf-enum" | "leaf-info" | "unknown",
      "value": string | number | null,    // Current value if visible (e.g., "Enabled", 42, "Auto")
      "options": string[] | null,         // Available options for leaf-enum (e.g., ["Mode 1", "Mode 2", "Auto"])
      "key_to_enter": string              // The keystroke that activates this entry (usually "Enter")
    }}
  ],
  "blocklist_flag": boolean,              // true if any dangerous keyword is visible on screen
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

Return only the JSON object. No other text."""

VLM_DEFAULT_PARAMS = {
    "temperature": 0.0,
    "max_tokens": 2048,
    "response_format": {"type": "json_object"}
}

DANGEROUS_KEYWORDS = ["Flash", "Secure Erase", "RAID", "Boot Order", "Password", "Set Password"]
