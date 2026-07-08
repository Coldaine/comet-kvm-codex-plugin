# R2 — Dead Code Wired to Nothing

**Severity:** 🟡 High
**Filed against:** PR #12 (`feat/mcp-tool-surface`)

---

## R2a — `trace/ledger.py`

**File:** `src/bios_sidecar/trace/ledger.py`

**Status:** Full implementation exists — `TraceLedger` class, `log_event()`, `export_run_trace_json()`. Zero references in any other file.

**Problem:** The runtime never instantiates `TraceLedger`. No `SESSION_CONNECTED`, `ACTION_EXECUTED`, `POLICY_DECIDED`, `HAZARD_DETECTED`, or any other events are ever recorded. The entire observability layer is dead.

**Remediation:**
1. Instantiate `TraceLedger` in `StatefulBiosRuntime.__init__()`
2. Call `self.trace.log_event(...)` at every state transition in `controller/runtime.py`:
   - Inside `connect_comet()` → log `SESSION_CONNECTED`
   - Inside `observe_state()` → log `FRAME_CAPTURED`, `OCR_COMPLETED`, `VLM_PARSED`, `STATE_NORMALIZED`
   - Inside `crawl_step()` → log `ACTION_EXECUTED`, `TRANSITION_OBSERVED`, `HAZARD_DETECTED`
   - Inside `apply_setting_change()` → log `APPROVAL_REQUESTED`, `APPROVAL_GRANTED`
   - Inside `abort_and_recover()` → log `RECOVERY_EXECUTED`, `RUN_ABORTED`

---

## R2b — `adapters/base.py` and `adapters/msi_click_bios.py`

**Files:**
- `src/bios_sidecar/adapters/base.py`
- `src/bios_sidecar/adapters/msi_click_bios.py`

**Status:** Both files exist with correct vendor metadata, blocklist keywords, and known capabilities. Zero references in any other file.

**Problem:** The adapter pattern is documented in the design plan (§15) but never wired. The normalizer in `perception/normalize.py` hardcodes MSI vendor detection by string-matching the screen title — the adapter's `normalize_label()`, `identify_module()`, and hazard classification are never called. The `CapabilityIndex` in `state/capability_index.py` pre-loads MSI priors directly without consulting the adapter.

**Remediation:**
1. Make `StatefulBiosRuntime` load the appropriate adapter based on detected vendor
2. Pass the adapter to `normalize_bios_state()` so it can use `adapter.normalize_label()` and `adapter.identify_module()`
3. Pass the adapter to `PolicyEngine` so it can use `adapter.hard_block_keywords` and `adapter.known_capabilities`
4. Fall back to `GenericUefiAdapter` when vendor is unknown

---

## R2c — `comet/hid.py`

**File:** `src/bios_sidecar/comet/hid.py`

**Status:** `HIDController` class with convenience methods (`press_up`, `press_down`, `press_enter`, etc.). Zero references.

**Problem:** The controller code calls `CometClient.send_combo()` directly instead of going through `HIDController`. The abstraction layer is dead.

**Remediation:** Either use `HIDController` in the controller modules (`crawl.py`, `navigate.py`, `mutate.py`) or delete the file and document that direct `CometClient` calls are the pattern.

---

## R2d — `policy/matrix.yaml`

**File:** `src/bios_sidecar/policy/matrix.yaml`

**Status:** Full YAML action matrix exists with all 4 policy profiles. Zero references.

**Problem:** `PolicyEngine.__init__()` only loads the YAML if `matrix_path` is explicitly passed. `StatefulBiosRuntime` never passes one, so the hardcoded Python dict in `_load_default_matrix()` is always used. Any policy change requires a code change.

**Remediation:**
```python
# In StatefulBiosRuntime.__init__():
import os
matrix_path = os.path.join(os.path.dirname(__file__), "..", "policy", "matrix.yaml")
self.policy_engine = PolicyEngine(
    approval_tracker=self.approval_tracker,
    matrix_path=matrix_path
)
```

---

## Order of remediation (deferred to follow-up work)

1. R2a (trace ledger) — highest value, enables operational observability
2. R2d (matrix.yaml) — quick wiring, enables config-driven policy changes
3. R2b (adapters) — architectural correctness, moderate effort
4. R2c (HID controller) — either use or delete
