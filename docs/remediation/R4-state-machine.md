# R4 — Runtime State Machine Is Decorative

**Severity:** 🟡 High
**Filed against:** PR #12 (`feat/mcp-tool-surface`)
**Design section:** §10 — Runtime state machine

---

## The gap

The design plan specifies a **guarded state machine** with explicit transitions:

```
UNCONFIGURED → DISCONNECTED → CONNECTED → OBSERVING → SYNCED
  ├─ crawl request → CRAWLING
  ├─ navigate request → NAVIGATING
  ├─ mutation request → AWAITING_APPROVAL
  └─ failure → DEGRADED
```

The implementation in `controller/runtime.py` has the `RuntimeState` enum and sets `self.state = RuntimeState.X` at method entry/exit, but **never checks the current state before allowing an operation**.

Concrete violations:

| Call sequence | Current behavior | Correct behavior |
|---|---|---|
| `crawl_step()` before `observe_state()` | Calls observe internally, then crawls | Should check state is CONNECTED or SYNCED |
| `apply_setting_change()` before `connect_comet()` | Crashes with `AttributeError` on `None.client` | Should raise `RuntimeError("Not connected")` |
| `observe_state()` during a crawl | Allowed | Should be blocked — already in CRAWLING |
| Double `connect_comet()` | Disconnects first, then reconnects | Should check state is DISCONNECTED |
| `navigate_to()` with no graph data | Returns failure after attempt | Should check state is SYNCED with graph data available |

---

## Required fix

Add a transition matrix that maps `(current_state, requested_method) → allowed/denied`:

```python
# In runtime.py
_TRANSITION_MATRIX = {
    RuntimeState.DISCONNECTED: {
        "connect_comet": RuntimeState.CONNECTED,
    },
    RuntimeState.CONNECTED: {
        "observe_state": RuntimeState.OBSERVING,
    },
    RuntimeState.OBSERVING: {
        # Transitions to SYNCED or DEGRADED based on result
    },
    RuntimeState.SYNCED: {
        "observe_state": RuntimeState.OBSERVING,
        "crawl_step": RuntimeState.CRAWLING,
        "navigate_to": RuntimeState.NAVIGATING,
        "propose_setting_change": RuntimeState.SYNCED,  # no-op
    },
    RuntimeState.CRAWLING: {
        # Stay in CRAWLING after each step, or back to SYNCED on completion
    },
    # ... etc
}
```

Add a guard method:

```python
async def _transition_to(self, method_name: str, target_state: RuntimeState):
    current = self.state
    allowed = _TRANSITION_MATRIX.get(current, {})
    if method_name not in allowed:
        raise RuntimeError(
            f"Invalid transition: {current.value} → {method_name}. "
            f"Allowed: {list(allowed.keys())}"
        )
    self.state = target_state
```

---

## Remediation checklist

- [ ] Define transition matrix as a module-level dict
- [ ] Add `_transition_to()` guard method
- [ ] Guard every public method in `StatefulBiosRuntime`
- [ ] Test invalid transitions raise `RuntimeError`
- [ ] Add `DEGRADED` → `SYNCED` recovery path (via fresh `observe_state`)
