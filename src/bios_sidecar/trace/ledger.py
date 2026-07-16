from __future__ import annotations
import uuid
import datetime
import json
import os
from typing import Dict, Any
from src.bios_sidecar.domain.models import TraceEvent
from src.bios_sidecar.domain.enums import EventClass
from src.bios_sidecar.state.store import SQLiteStore

class TraceLedger:
    def __init__(self, store: SQLiteStore, run_directory: str = "runs"):
        self.store = store
        self.run_directory = run_directory
        os.makedirs(run_directory, exist_ok=True)

    async def log_event(
        self,
        run_id: str,
        event_type: EventClass,
        state_before: str = None,
        state_after: str = None,
        requested_action: Dict[str, Any] = None,
        policy_decision: Dict[str, Any] = None,
        artifacts: Dict[str, Any] = None
    ) -> TraceEvent:
        """Saves trace event to persistent SQLite database."""
        event_id = f"evt_{uuid.uuid4().hex[:12]}"
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

        evt = TraceEvent(
            event_id=event_id,
            run_id=run_id,
            timestamp=timestamp,
            event_type=event_type,
            state_before=state_before,
            state_after=state_after,
            requested_action=requested_action,
            policy_decision=policy_decision,
            artifacts=artifacts or {}
        )
        self.store.save_trace_event(evt)
        return evt

    def export_run_trace_json(self, run_id: str) -> str:
        """Exports a full run trace event sequence to a replayable JSON format."""
        events = self.store.list_trace_events(run_id)
        serialized = [e.to_dict() for e in events]

        export_file = os.path.join(self.run_directory, f"trace_{run_id}.json")
        with open(export_file, "w", encoding="utf-8") as f:
            json.dump(serialized, f, indent=2)
        return export_file
