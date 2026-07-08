# Action-Time Executable Safety Policy

The Stateful BIOS Sidecar is governed by an automated, executable policy model (configured in `src/bios_sidecar/policy/matrix.yaml` and evaluated by `src/bios_sidecar/policy/engine.py`). This ensures that the primary driver agent cannot execute unsafe or destructive inputs in the BIOS.

## 1. Operating Modes (Profiles)

| Mode | Purpose | Allowed actions |
|------|---------|-----------------|
| `observe_only` | Capture and parse current state | Screenshot/OCR / VLM only. Keystrokes are strictly blocked. |
| `read_only_crawl` | Build graph/map safe regions without mutation | Arrows, Esc, safe context-gated Enter on submenu nodes. F10/save is strictly blocked. |
| `supervised_mutation` | Apply approved, scoped settings changes | Context-gated Enter/Escape. F10/save allowed ONLY with human-granted approval token. |
| `admin_debug` | Arbitrary direct low-level KVM overrides | Raw HID (logged and restricted to troubleshooting). |

## 2. Gating of the Enter Key

`Enter` is not globally safe or unsafe. It is dynamically context-gated by the active layout screen kind:
- **Allowed:** Entering a safe `submenu` (e.g. going from Settings into Advanced) during read-only sessions.
- **Blocked:** Entering a `setting` value list (which would open mutation options) during a crawl session.
- **Requires Approval:** Entering setting controls or modal selections during a tuning run.

## 3. Dangerous Screen Keywords / Blocklists

If any of these keywords are visible either on screen titles or control options, the policy engine activates a **Hard Blocklist Gate**:
- "Flash" / "M-FLASH"
- "Secure Erase"
- "RAID"
- "Boot Order"
- "Password" / "Set Password"

In Blocklist mode, the only allowed keypress is **Escape** (to back out safely). Standard ArrowDown, Enter, or F10 keys are disabled immediately.
