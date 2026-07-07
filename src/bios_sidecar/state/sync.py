from __future__ import annotations
import logging
from typing import Optional, Dict, Any, Tuple
from src.bios_sidecar.domain.models import BiosState, StateNode
from src.bios_sidecar.state.matcher import StateMatcher

LOG = logging.getLogger("bios_sidecar.state.sync")

class StateSyncer:
    def __init__(self, matcher: StateMatcher):
        self.matcher = matcher
        self.current_matched_node: Optional[StateNode] = None
        self.is_synced: bool = False
        self.sync_confidence: float = 0.0

    def verify_and_align(self, live_state: BiosState) -> Tuple[bool, Optional[str]]:
        """
        Verify if the current live state matches a known node in our graph,
        and align the tracker with that node.
        """
        phash = live_state.frame.perceptual_hash

        # We can construct mock ocr hash for indexing
        from src.bios_sidecar.state.hashing import calculate_state_semantic_hash
        ocr_hash = live_state.frame.sha256[:16] # quick dummy shorthand
        v = live_state.bios.vendor
        b = live_state.bios.board_hint
        t = live_state.location.screen_title or "unknown"
        p = live_state.location.breadcrumb
        sem_hash = calculate_state_semantic_hash(v, b, t, p)

        node, confidence = self.matcher.match_state(phash, ocr_hash, sem_hash)
        if node and confidence >= 0.75:
            self.current_matched_node = node
            self.is_synced = True
            self.sync_confidence = confidence
            return True, node.node_id
        else:
            self.current_matched_node = None
            self.is_synced = False
            self.sync_confidence = 0.0
            return False, None
