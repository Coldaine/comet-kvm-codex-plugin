from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any, Optional, List, Dict
from src.bios_sidecar.domain.enums import StateKind, ControlRole, RiskClass, EventClass

@dataclass
class FrameMetadata:
    screenshot_id: str
    sha256: str
    perceptual_hash: str
    resolution: List[int]  # [width, height]
    captured_at: str       # ISO 8601 string

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> FrameMetadata:
        return cls(**d)

@dataclass
class BiosMetadata:
    vendor: str
    board_hint: str
    family: str
    mode: str  # e.g., "advanced", "ez"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> BiosMetadata:
        return cls(**d)

@dataclass
class LocationMetadata:
    screen_kind: StateKind
    top_module: str                          # e.g., "SETTINGS", "OC"
    breadcrumb: List[str]                   # e.g., ["SETTINGS", "Advanced"]
    screen_title: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["screen_kind"] = self.screen_kind.value
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> LocationMetadata:
        d = dict(d)
        d["screen_kind"] = StateKind(d["screen_kind"])
        return cls(**d)

@dataclass
class SelectionMetadata:
    selected_index: Optional[int]
    label: Optional[str]
    value: Optional[str]
    bbox: Optional[List[int]] = None  # [x, y, w, h] or similar bounding box
    confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> SelectionMetadata:
        return cls(**d)

@dataclass
class ControlEntry:
    control_id: str
    label: str
    value: Optional[str]
    role: ControlRole
    selected: bool
    risk: RiskClass
    bbox: Optional[List[int]] = None  # [x, y, w, h]
    options: Optional[List[str]] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["role"] = self.role.value
        d["risk"] = self.risk.value
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> ControlEntry:
        d = dict(d)
        d["role"] = ControlRole(d["role"])
        d["risk"] = RiskClass(d["risk"])
        return cls(**d)

@dataclass
class ModalMetadata:
    present: bool
    type: Optional[str] = None
    message: Optional[str] = None
    options: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> ModalMetadata:
        return cls(**d)

@dataclass
class RiskStatus:
    blocklist_flag: bool
    blocklist_keywords: List[str] = field(default_factory=list)
    hazards: List[str] = field(default_factory=list)
    policy_class: str = "context_gated"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> RiskStatus:
        return cls(**d)

@dataclass
class ActionPolicies:
    safe: List[str] = field(default_factory=list)
    context_gated: List[str] = field(default_factory=list)
    approval_required: List[str] = field(default_factory=list)
    blocked: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> ActionPolicies:
        return cls(**d)

@dataclass
class ConfidenceMetrics:
    ocr: float
    vlm: float
    state: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> ConfidenceMetrics:
        return cls(**d)

@dataclass
class BiosState:
    state_id: str
    run_id: str
    device_id: str
    frame: FrameMetadata
    bios: BiosMetadata
    location: LocationMetadata
    selection: SelectionMetadata
    controls: List[ControlEntry] = field(default_factory=list)
    modal: ModalMetadata = field(default_factory=lambda: ModalMetadata(present=False))
    risk: RiskStatus = field(default_factory=lambda: RiskStatus(blocklist_flag=False))
    actions: ActionPolicies = field(default_factory=ActionPolicies)
    confidence: ConfidenceMetrics = field(default_factory=lambda: ConfidenceMetrics(1.0, 1.0, 1.0))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state_id": self.state_id,
            "run_id": self.run_id,
            "device_id": self.device_id,
            "frame": self.frame.to_dict(),
            "bios": self.bios.to_dict(),
            "location": self.location.to_dict(),
            "selection": self.selection.to_dict(),
            "controls": [c.to_dict() for c in self.controls],
            "modal": self.modal.to_dict(),
            "risk": self.risk.to_dict(),
            "actions": self.actions.to_dict(),
            "confidence": self.confidence.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> BiosState:
        return cls(
            state_id=d["state_id"],
            run_id=d["run_id"],
            device_id=d["device_id"],
            frame=FrameMetadata.from_dict(d["frame"]),
            bios=BiosMetadata.from_dict(d["bios"]),
            location=LocationMetadata.from_dict(d["location"]),
            selection=SelectionMetadata.from_dict(d["selection"]),
            controls=[ControlEntry.from_dict(c) for c in d["controls"]],
            modal=ModalMetadata.from_dict(d["modal"]),
            risk=RiskStatus.from_dict(d["risk"]),
            actions=ActionPolicies.from_dict(d["actions"]),
            confidence=ConfidenceMetrics.from_dict(d["confidence"]),
        )

@dataclass
class StateNode:
    node_id: str
    visual_hash: str
    ocr_hash: str
    semantic_hash: str
    volatile_regions: List[str] = field(default_factory=list)
    representative_state_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> StateNode:
        return cls(**d)

@dataclass
class EdgeAction:
    type: str # e.g. "KEY"
    key: str # e.g. "ENTER"
    policy_decision: str = "allowed"
    policy_profile: str = "read_only_crawl"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> EdgeAction:
        return cls(**d)

@dataclass
class EdgeEvidence:
    before_screenshot: str
    after_screenshot: str
    before_state: str
    after_state: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> EdgeEvidence:
        return cls(**d)

@dataclass
class GraphEdge:
    edge_id: str
    from_node: str
    action: EdgeAction
    to_node: str
    transition_type: str
    evidence: EdgeEvidence

    def to_dict(self) -> Dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "from_node": self.from_node,
            "action": self.action.to_dict(),
            "to_node": self.to_node,
            "transition_type": self.transition_type,
            "evidence": self.evidence.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> GraphEdge:
        return cls(
            edge_id=d["edge_id"],
            from_node=d["from_node"],
            action=EdgeAction.from_dict(d["action"]),
            to_node=d["to_node"],
            transition_type=d["transition_type"],
            evidence=EdgeEvidence.from_dict(d["evidence"]),
        )

@dataclass
class CapabilityPath:
    breadcrumb: List[str]
    label: str
    last_seen_value: Optional[str]
    node_id: str
    control_id: str
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> CapabilityPath:
        return cls(**d)

@dataclass
class CapabilityEntry:
    capability_id: str
    canonical_name: str
    aliases: List[str]
    vendor: str
    board_family: str
    paths: List[CapabilityPath]
    risk: RiskClass
    mutation_policy: str
    validation: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["risk"] = self.risk.value
        d["paths"] = [p.to_dict() for p in self.paths]
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> CapabilityEntry:
        d = dict(d)
        d["risk"] = RiskClass(d["risk"])
        d["paths"] = [CapabilityPath.from_dict(p) for p in d["paths"]]
        return cls(**d)

@dataclass
class TraceEvent:
    event_id: str
    run_id: str
    timestamp: str
    event_type: EventClass
    state_before: Optional[str] = None
    requested_action: Optional[Dict[str, Any]] = None
    policy_decision: Optional[Dict[str, Any]] = None
    state_after: Optional[str] = None
    artifacts: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["event_type"] = self.event_type.value if isinstance(self.event_type, EventClass) else self.event_type
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> TraceEvent:
        d = dict(d)
        d["event_type"] = EventClass(d["event_type"])
        return cls(**d)
