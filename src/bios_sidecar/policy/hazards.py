from __future__ import annotations
import logging
from typing import List
from src.bios_sidecar.domain.models import BiosState
from src.bios_sidecar.domain.enums import StateKind, RiskClass

LOG = logging.getLogger("bios_sidecar.policy.hazards")

BLOCKLIST_KEYWORDS = ["Flash", "Secure Erase", "RAID", "Boot Order", "Password", "Set Password"]

class HazardDetector:
    def __init__(self, blocklist_keywords: List[str] = None):
        self.blocklist_keywords = blocklist_keywords or BLOCKLIST_KEYWORDS

    def analyze_hazards(self, state: BiosState) -> List[str]:
        """Scans state kind, selected control, and labels for active hazards."""
        hazards = []

        # 1. State kind dangers
        if state.location.screen_kind in (StateKind.FLASH_UTILITY, StateKind.SECURE_ERASE, StateKind.PASSWORD_PROMPT):
            hazards.append(f"destructive_screen_kind:{state.location.screen_kind.value}")

        # 2. Blocklist keyword matches on titles or breadcrumbs
        title = (state.location.screen_title or "").lower()
        breadcrumb = " ".join(state.location.breadcrumb).lower()
        for kw in self.blocklist_keywords:
            kw_lower = kw.lower()
            if kw_lower in title:
                hazards.append(f"blocklist_keyword_in_title:{kw}")
            if kw_lower in breadcrumb:
                hazards.append(f"blocklist_keyword_in_breadcrumb:{kw}")

        # 3. Control entry dangers (selected blocked control or active options)
        for ctrl in state.controls:
            if ctrl.risk == RiskClass.BLOCKED:
                hazards.append(f"blocked_control_on_screen:{ctrl.label}")

        # 4. Global blocklist flag trigger
        if state.risk.blocklist_flag:
            hazards.append("explicit_blocklist_flag_triggered")

        return list(set(hazards))
