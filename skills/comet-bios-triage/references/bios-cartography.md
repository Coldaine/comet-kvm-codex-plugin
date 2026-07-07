# BIOS Cartography (Design Draft)

> **Status:** Draft from prior design session (2026-07-07). Partially reconciled with `docs/decisions.md` (D3, D4, D7, D8) and `docs/NORTH_STAR.md` cartography spike scope. Remaining areas to update: state engine integration and VLM prompting pattern.

## Mission Statement
**To autonomously map the safe, tunable surface area of an unknown BIOS via KVM, generating a semantic UI index that enables deterministic hardware tuning without risking destructive state changes.**

## Component Purpose
The Automated UI Cartographer is a bounded discovery engine. Its sole job is to identify *where* a setting is, *what type* of UI element it is (dropdown, text field, toggle), and *how* to interact with it, while strictly avoiding dangerous firmware utilities.

## Strategy: Handling the "Incomplete Tree" (Bounded & Lazy Enumeration)
Mapping 100% of a modern BIOS is impossible and dangerous. The mapping strategy uses **Bounded Enumeration** combined with **Lazy Expansion**.

1.  **Strict Blocklisting**: The VLM is prompted to immediately abort and retreat if it detects OCR keywords like "Flash", "Secure Erase", "RAID", "Boot Order", or "Password". This prevents the crawler from entering volatile or destructive zones.
2.  **Targeted Allowlisting**: The crawler only explores tabs matching "OC", "Tweaker", "Extreme", "CPU", or "DRAM". This ensures 95% of the mapped tree is relevant to specific triage workflows (like 14900KF HWiNFO triage).
3.  **Lazy Expansion**: The initial run only maps the *root menus* and *first-level submenus*. Deep sub-menus (e.g., specific memory sub-timings) are left unexplored. This keeps the initial mapping fast (under 5 minutes) and prevents infinite recursion.
4.  **On-Demand Probing**: If the Outer LLM later requests a setting not in the map, it triggers a targeted, one-off search/probe just for that specific branch, appending it to the master tree. The tree grows organically.

## The Output: Semantic Capability Index
The Cartographer compiles its findings into a **Semantic Capability Index** JSON file saved to the runtime map store: on-Comet storage if verified, otherwise the host-side plugin data directory. It strips visual noise and presents only actionable controls.

**Example Structure:**
```json
{
  "mapped_settings": {
    "CPU Lite Load": {
      "path": ["OC Tab", "DigitAll Power", "CPU Lite Load"],
      "ui_type": "DROPDOWN",
      "available_options": ["Mode 1", "Mode 2", "Mode 3", "Mode 4", "Auto"],
      "interaction_keys": ["ENTER", "DOWN", "ENTER"]
    },
    "DRAM Frequency": {
      "path": ["OC Tab", "DRAM Setting", "DRAM Frequency"],
      "ui_type": "DROPDOWN",
      "available_options": ["Auto", "DDR5-5600", "DDR5-6000"],
      "interaction_keys": ["ENTER", "DOWN", "ENTER"]
    }
  },
  "unmapped_but_located_tabs": ["Advanced", "Security", "Boot"],
  "last_updated": "YYYY-MM-DDTHH:MM:SSZ"
}
```

## How the Outer LLM Uses This Index
*   **Known Settings**: If the LLM wants to change a known setting (e.g., "Change CPU Lite Load to Mode 3"), it checks the Index for the exact `path` and `interaction_keys`, bypassing the VLM for navigation and deterministically firing keys via KVM MCP.
*   **Unknown Settings**: If a requested setting is missing, the LLM triggers the **Lazy Expansion** routine to find, map its UI type, and append it to the Index before interacting.
*   **Read-Only Checks**: To check a value, the LLM navigates using the Index `path` and uses the VLM *purely* to read the current value, leaving the Index untouched.
