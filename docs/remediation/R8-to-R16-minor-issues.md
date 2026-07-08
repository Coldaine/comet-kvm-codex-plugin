# R8 — Mutation Value Selection Is Naive

**Severity:** 🟡 High
**Design section:** §14 — Mutation workflow

**File:** `src/bios_sidecar/controller/mutate.py`, method `apply_setting_change()`

**Problem:** After pressing Enter to open a value dropdown, the mutation code always presses ArrowDown once then Enter — regardless of the actual value structure:

```python
await client.send_combo("ArrowDown")
await self.settler.wait_for_settle(client)
await client.send_combo("Enter")
```

This assumes all BIOS dropdowns work the same way and the desired value is always one ArrowDown away. In reality:
- Some dropdowns need N ArrowDown/ArrowUp presses to reach the target
- Some dropdowns accept direct text input
- Some are toggles that cycle with each Enter press

**Remediation:** Make value selection driven by VLM data. The VLM parse includes `entries[].options` for leaf-enum types. Use that to calculate the correct ArrowDown count:

```python
target_idx = options.index(desired_value)
current_idx = options.index(current_value)
delta = (target_idx - current_idx) % len(options)
for _ in range(delta):
    await client.send_combo("ArrowDown")
    await asyncio.sleep(0.1)
```

---

# R9 — Missing MCP Resources and Namespace

**Severity:** 🟡 High
**Design section:** §3B — MCP façade, §4 — Control-plane design

**Missing resources:**
- `bios://ocr/current` — no resource returns current OCR state
- `bios://trace/{run_id}` — no parameterized trace resource
- `bios://schema/state` — no BiosState schema resource
- `bios://schema/transition` — no Transition schema resource

**Missing namespace:** The design plan says legacy HID tools should be namespaced under `comet.raw.*`. Currently they all use `kvm_*` names. A `comet.raw.*` tool suite should be created (deprecating but not removing `kvm_*`):

```python
@mcp.tool(name="comet.raw.send_key", ...)
async def comet_raw_send_key(combo: str) -> dict:
    """Debug/admin tool: send raw key chord. Use bios.* tools for normal operations."""
    _verify_admin_profile()
    return await _require_client().send_combo(combo)
```

---

# R10 — Package Structure Missing `__init__.py`

**Severity:** 🟡 High

**Problem:** Zero `__init__.py` files exist anywhere under `src/bios_sidecar/`. While Python 3.3+ supports namespace packages without them, this is fragile:

- Some tools (`pytest`, `mypy`, `pyinstaller`) may not discover the package correctly
- `from src.bios_sidecar.domain import enums` won't work as a relative import in an installed package
- IDEs may not recognize the structure as a Python package

**Remediation:** Create minimal `__init__.py` files:

```python
# src/bios_sidecar/__init__.py
"""BIOS KVM sidecar runtime."""

# src/bios_sidecar/domain/__init__.py
from . import enums, models, schemas

# src/bios_sidecar/comet/__init__.py
from .client import CometClient
from .session import SessionManager

# ... same pattern for all subpackages
```

---

# R12 — Test Fixture Directory Missing

**Severity:** 🟢 Medium

**Problem:** There are no golden screenshots, expected VLM JSON outputs, or trace examples in the repository. The `.gitignore` ignores `state/*` and image files but doesn't carve out a fixture directory exception.

**Remediation:**
- Create `tests/fixtures/` directory with `.gitkeep`
- Add `.gitignore` exception: `!tests/fixtures/`
- Add synthetic BIOS screenshot fixtures (once screenshot policy is settled)
- Add expected VLM JSON outputs matching `docs/vlm-prompt-contract.md` schema
- Add expected trace JSON examples

---

# R13 — Missing Skill Reference Docs

**Severity:** 🟢 Medium
**Design section:** §3A — Skill router

The design plan calls for these reference docs under `skills/comet-bios-triage/references/`:

| Plan says | Status |
|---|---|
| `action-time-router.md` | ❌ Missing |
| `safety-policy.md` | ✅ Created |
| `state-model.md` | ✅ Created |
| `msi-z690-adapter.md` | ❌ Missing — describes how the adapter wires into the runtime |
| `mutation-workflow.md` | ❌ Missing — describes the propose→approve→apply→verify flow |
| `capability-index.md` | ❌ Missing — describes how the index maps settings to screens |

---

# R14 — README.md Not Updated

**Severity:** 🟢 Medium

**Problem:** The repo `README.md` still describes the old single-file MCP server. It doesn't mention:

- The `src/bios_sidecar/` package structure
- The `bios_*` stateful MCP tools
- The policy engine and safety model
- The SQLite graph store
- The test suite and how to run it
- The skill references and their purpose

**Remediation:** Update `README.md` to cover:
1. Architecture overview (layer diagram)
2. Quick start: how to run the MCP server
3. MCP tool namespaces (`kvm_*` legacy, `bios_*` stateful)
4. How the safety policy works
5. How to run tests
6. Project authority order (point to `docs/NORTH_STAR.md`)

---

# R15 — GitHub Issues Alignment

**Severity:** 🟢 Medium

**Current state:** 7 open issues on GitHub. PRs #11 and #12 are open and stacked.

**Observations:**
- Issue #10 ("Implement BIOS cartography spike") is the **root issue** that PRs #11/#12 should close
- Issue #3 ("Run first live-safe Comet MCP smoke sequence") is a prerequisite — it's not done yet
- Issue #2 ("Install and verify host Tesseract for Comet OCR") is a prerequisite — not done
- Issue #4 ("Implement MSI Z690 BIOS state-machine workflow") overlaps significantly with the sidecar PRs
- Issue #5 ("Integrate HWiNFO log watcher") is not addressed by the sidecar PRs — still outstanding
- Issue #6 ("Evaluate ATX, MSD, and multi-target expansion") — pre-decision, no action needed

**Recommended actions:**
1. Link PRs #11/#12 to Issue #10 in PR descriptions
2. Close Issue #3 and Issue #2 as "blocked by live Comet access" — they depend on live Comet access which is separate from the offline implementation
3. Add Issue #4 to the tracked scope of the remediation pass
4. Leave Issue #5 and #6 as future work

---

# R16 — Agent Integration View Missing

**Severity:** 🟢 Medium
**Design section:** §18 — Agent integration

**Problem:** The design plan says the main agent should see a compact status view:

```json
{
  "current_state": {},
  "known_capabilities": [],
  "safe_actions": [],
  "blocked_actions": [],
  "graph_summary": {},
  "recommended_next_steps": []
}
```

Currently, the agent must call 4+ separate resources/tools to assemble this view. There's no `bios_status_briefing()` tool that returns the combined view.

**Remediation:** Add a `bios_status_briefing` tool that aggregates:
- Current state (from `bios://state/current`)
- Capability count (from `bios://capabilities/current`)
- Safe/blocked actions (from the policy engine's last evaluation)
- Graph coverage (from `bios://graph/current`)
- Recommended next steps (based on current mode and graph state)
