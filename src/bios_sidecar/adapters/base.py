from __future__ import annotations
from typing import List, Dict, Any

class BiosAdapter:
    vendor: str = "generic"
    families: List[str] = ["generic_uefi"]
    known_modules: List[str] = []
    hard_block_keywords: List[str] = []
    known_capabilities: Dict[str, Any] = {}

    def normalize_label(self, raw_label: str) -> str:
        """Cleans and normalizes labels."""
        return raw_label.strip()

    def identify_module(self, title: str) -> str:
        """Categorizes submodules."""
        return "SETTINGS"
