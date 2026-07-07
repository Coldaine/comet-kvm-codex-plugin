from __future__ import annotations
import logging
from typing import Optional, Tuple, List
from src.bios_sidecar.domain.models import StateNode
from src.bios_sidecar.state.graph import BiosGraph

LOG = logging.getLogger("bios_sidecar.state.matcher")

def hamming_distance(hex1: str, hex2: str) -> int:
    """Computes the bitwise Hamming distance between two hex hashes of equal length."""
    if len(hex1) != len(hex2):
        return 999
    try:
        val1 = int(hex1, 16)
        val2 = int(hex2, 16)
        diff = val1 ^ val2
        # Count set bits
        return bin(diff).count("1")
    except ValueError:
        return 999

class StateMatcher:
    def __init__(self, graph: BiosGraph):
        self.graph = graph
        self.max_hamming_threshold = 12  # Out of 64 bits (approx 80%+ similarity)

    def match_state(self, live_phash: str, ocr_hash: str, semantic_hash: str) -> Tuple[Optional[StateNode], float]:
        """
        Matches a live screen to an existing graph node.
        Returns:
            (matched_node, confidence_score)
        """
        # Phase 1: Exact Semantic Hash Match (fastest, safest)
        for node in self.graph.nodes.values():
            if node.semantic_hash == semantic_hash:
                LOG.info("Exact semantic hash match found for node %s", node.node_id)
                return node, 1.0

        # Phase 2: Perceptual Hash match (Hamming distance)
        best_node: Optional[StateNode] = None
        best_distance = 999

        for node in self.graph.nodes.values():
            dist = hamming_distance(live_phash, node.visual_hash)
            if dist < best_distance:
                best_distance = dist
                best_node = node

        if best_node and best_distance <= self.max_hamming_threshold:
            # Scale distance to [0..1] similarity score
            similarity = 1.0 - (best_distance / 64.0)
            LOG.info("Visual perceptual hash match found with distance %d (similarity %.2f) at node %s",
                     best_distance, similarity, best_node.node_id)
            return best_node, similarity

        # Phase 3: OCR text overlap similarity fallback
        for node in self.graph.nodes.values():
            if node.ocr_hash == ocr_hash:
                LOG.info("Exact OCR fingerprint hash match found for node %s", node.node_id)
                return node, 0.90

        LOG.info("No matching state found in active graph nodes.")
        return None, 0.0
