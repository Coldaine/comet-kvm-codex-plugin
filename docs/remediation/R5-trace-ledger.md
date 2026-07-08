# R5 — Trace Ledger Never Called

**Severity:** 🔴 Critical
**Filed against:** PR #12 (`feat/mcp-tool-surface`)
**Design section:** §16 — Trace and evidence design

---

## The gap

The design plan specifies an event-sourced trace system where every action, policy decision, and state transition is recorded as a `TraceEvent` for replay and auditing. The plan lists 13 required event classes:

| Event | Purpose | Currently recorded? |
|---|---|---|
| `SESSION_CONNECTED` | KVM session start | ❌ |
| `FRAME_CAPTURED` | Screenshot evidence | ❌ |
| `OCR_COMPLETED` | OCR evidence | ❌ |
| `VLM_PARSED` | Model parse evidence | ❌ |
| `STATE_NORMALIZED` | Canonical BIOS state | ❌ |
| `POLICY_DECIDED` | Allow/block/approval | ❌ |
| `ACTION_EXECUTED` | HID action | ❌ |
| `TRANSITION_OBSERVED` | Before/after state | ❌ |
| `HAZARD_DETECTED` | Blocked region | ❌ |
| `APPROVAL_REQUESTED` | Mutation/save approval | ❌ |
| `APPROVAL_GRANTED` | Human authorized | ❌ |
| `RECOVERY_EXECUTED` | Release/backtrack | ❌ |
| `RUN_ABORTED` | Controlled stop | ❌ |

**Zero trace events are ever recorded.** The `TraceLedger` class exists with correct implementation but is never instantiated or called.

---

## Why it matters

Without the trace ledger:

- **No audit trail** — you cannot reconstruct what happened during a failed run
- **No replay capability** — the `bios_export_trace` MCP tool returns an empty trace
- **No debugging data** — when a crawl or mutation fails, there is no record of what led to the failure
- **The design plan's §16 is entirely unimplemented** despite `trace/ledger.py` existing

---

## Remediation

Wire `TraceLedger` into `StatefulBiosRuntime` and call it at every lifecycle point:

### 1. In `StatefulBiosRuntime.__init__()`:

```python
from src.bios_sidecar.trace.ledger import TraceLedger
# ...
self.trace = TraceLedger(store=self.store)
```

### 2. In `connect_comet()`:

```python
await self.trace.log_event(
    run_id=self.run_id,
    event_type=EventClass.SESSION_CONNECTED,
    artifacts={"host": host, "device_id": self.device_id}
)
```

### 3. In `observe_state()` (inside the observe call or as a wrapper):

```python
self.trace.log_event(run_id, EventClass.FRAME_CAPTURED, artifacts=...)
self.trace.log_event(run_id, EventClass.OCR_COMPLETED, artifacts=...)
self.trace.log_event(run_id, EventClass.VLM_PARSED, artifacts=...)
self.trace.log_event(run_id, EventClass.STATE_NORMALIZED, state_after=state.state_id, artifacts=...)
```

### 4. In `crawl_step()`:

```python
self.trace.log_event(
    run_id, EventClass.ACTION_EXECUTED,
    state_before=current_state.state_id,
    requested_action={"type": "KEY", "key": candidate_key},
    policy_decision=decision.to_dict(),
    state_after=new_state.state_id,
    artifacts={"edge_id": edge.edge_id if edge else None}
)
```

### 5. In `abort_and_recover()`:

```python
self.trace.log_event(run_id, EventClass.RECOVERY_EXECUTED, ...)
self.trace.log_event(run_id, EventClass.RUN_ABORTED, ...)
```

---

## Remediation checklist

- [ ] Instantiate `TraceLedger` in `StatefulBiosRuntime.__init__()`
- [ ] Call `log_event()` on every lifecycle transition in `runtime.py`
- [ ] Call `log_event()` on every policy decision in `crawl.py` and `mutate.py`
- [ ] Call `log_event()` on every approval action in `mutate.py`
- [ ] Verify `bios_export_trace` returns non-empty output after a simulated run
