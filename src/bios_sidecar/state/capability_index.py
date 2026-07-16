from __future__ import annotations
import logging
from typing import Dict, Optional
from src.bios_sidecar.domain.models import CapabilityEntry, CapabilityPath
from src.bios_sidecar.domain.enums import RiskClass
from src.bios_sidecar.state.store import SQLiteStore

LOG = logging.getLogger("bios_sidecar.state.capabilities")

# Stable priors/known properties for MSI Click BIOS on Z690
KNOWN_MUTABILITY_MAP = {
    "cpu_lite_load_mode": {
        "canonical_name": "CPU Lite Load Mode",
        "aliases": ["CPU Lite Load", "CPU Lite Load Control", "CPU Lite Load Mode"],
        "risk": RiskClass.MEDIUM,
        "mutation_policy": "supervised_one_setting"
    },
    "pl1": {
        "canonical_name": "Power Limit 1",
        "aliases": ["Long Duration Power Limit (W)", "PL1", "Power Limit 1"],
        "risk": RiskClass.HIGH,
        "mutation_policy": "supervised_one_setting"
    },
    "pl2": {
        "canonical_name": "Power Limit 2",
        "aliases": ["Short Duration Power Limit (W)", "PL2", "Power Limit 2"],
        "risk": RiskClass.HIGH,
        "mutation_policy": "supervised_one_setting"
    },
    "cpu_cooler_tuning": {
        "canonical_name": "CPU Cooler Tuning",
        "aliases": ["CPU Cooler Tuning", "Cooler Type"],
        "risk": RiskClass.MEDIUM,
        "mutation_policy": "supervised_one_setting"
    }
}

class CapabilityIndex:
    def __init__(self, store: SQLiteStore):
        self.store = store
        self.capabilities: Dict[str, CapabilityEntry] = {}
        self.reload_from_store()

    def reload_from_store(self):
        self.capabilities = {c.capability_id: c for c in self.store.list_capabilities()}
        # If empty, pre-initialize based on MSI Click BIOS priors
        if not self.capabilities:
            for cid, info in KNOWN_MUTABILITY_MAP.items():
                self.capabilities[cid] = CapabilityEntry(
                    capability_id=cid,
                    canonical_name=info["canonical_name"],
                    aliases=info["aliases"],
                    vendor="msi",
                    board_family="z690",
                    paths=[],
                    risk=info["risk"],
                    mutation_policy=info["mutation_policy"],
                    validation={"external_tool": "HWiNFO", "required_after_change": True}
                )
                self.store.save_capability(self.capabilities[cid])
            LOG.info("Pre-initialized capability index with %d MSI Z690 priors", len(self.capabilities))

    def register_discovered_setting(
        self, label: str, value: str, breadcrumb: list[str], node_id: str, control_id: str
    ):
        """When the crawler discovers a setting, link it to the capability index."""
        # Find matching capability by search aliases (case insensitive)
        matched_cid = None
        for cid, entry in self.capabilities.items():
            if any(alias.lower() == label.lower() for alias in entry.aliases):
                matched_cid = cid
                break

        if not matched_cid:
            # Create a brand new ad-hoc capability entry
            matched_cid = label.lower().replace(" ", "_").replace("(", "").replace(")", "")
            self.capabilities[matched_cid] = CapabilityEntry(
                capability_id=matched_cid,
                canonical_name=label,
                aliases=[label],
                vendor="msi",
                board_family="z690",
                paths=[],
                risk=RiskClass.MEDIUM,
                mutation_policy="supervised_one_setting",
                validation={}
            )

        # Add pathway to setting if not already present
        entry = self.capabilities[matched_cid]
        path_exists = any(p.node_id == node_id and p.control_id == control_id for p in entry.paths)
        if not path_exists:
            entry.paths.append(CapabilityPath(
                breadcrumb=breadcrumb,
                label=label,
                last_seen_value=value,
                node_id=node_id,
                control_id=control_id,
                confidence=1.0
            ))
            self.store.save_capability(entry)
            LOG.info("Linked path for capability '%s' at node %s", entry.canonical_name, node_id)

    def resolve_capability_by_handle(self, handle: str) -> Optional[CapabilityEntry]:
        """Resolves capability by ID, name, or one of its aliases."""
        handle_l = handle.lower()
        if handle_l in self.capabilities:
            return self.capabilities[handle_l]

        for cap in self.capabilities.values():
            if cap.canonical_name.lower() == handle_l:
                return cap
            if any(alias.lower() == handle_l for alias in cap.aliases):
                return cap
        return None
