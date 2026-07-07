from __future__ import annotations
import uuid
import datetime
from typing import Optional, Dict, Any
from src.bios_sidecar.state.store import SQLiteStore

class ApprovalTracker:
    def __init__(self, store: SQLiteStore):
        self.store = store

    def request_approval(self, plan_id: str) -> str:
        """Create a pending approval token."""
        approval_id = f"apprv_{uuid.uuid4().hex[:12]}"
        approved_at = ""
        self.store.save_approval(
            approval_id=approval_id,
            plan_id=plan_id,
            approved_at=approved_at,
            approved_by="",
            status="pending"
        )
        return approval_id

    def grant_approval(self, approval_id: str, approved_by: str) -> bool:
        """Grants/authorizes a pending approval token."""
        rec = self.store.get_approval(approval_id)
        if rec and rec["status"] == "pending":
            now_str = datetime.datetime.now().isoformat()
            self.store.save_approval(
                approval_id=approval_id,
                plan_id=rec["plan_id"],
                approved_at=now_str,
                approved_by=approved_by,
                status="granted"
            )
            return True
        return False

    def is_approved(self, approval_id: str) -> bool:
        """Verifies if a token has been approved/granted."""
        rec = self.store.get_approval(approval_id)
        return rec is not None and rec["status"] == "granted"
