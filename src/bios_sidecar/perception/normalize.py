from __future__ import annotations
import uuid
import logging
from typing import Any, Dict, List, Optional
from src.bios_sidecar.domain.models import (
    BiosState, FrameMetadata, BiosMetadata, LocationMetadata,
    SelectionMetadata, ControlEntry, ModalMetadata, RiskStatus,
    ActionPolicies, ConfidenceMetrics
)
from src.bios_sidecar.domain.enums import StateKind, ControlRole, RiskClass
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from src.bios_sidecar.adapters.base import BiosAdapter

LOG = logging.getLogger("bios_sidecar.perception.normalize")

DANGEROUS_WORDS = ["Flash", "Secure Erase", "RAID", "Boot Order", "Password", "Set Password"]

def parse_state_kind(title: Optional[str]) -> StateKind:
    if not title:
        return StateKind.UNKNOWN
    t = title.lower()
    if "ez mode" in t:
        return StateKind.EZ_MODE
    elif "settings" in t:
        if "advanced" in t:
            return StateKind.SETTING_LIST
        return StateKind.MENU_LIST
    elif "m-flash" in t or "flash" in t:
        return StateKind.FLASH_UTILITY
    elif "secure erase" in t:
        return StateKind.SECURE_ERASE
    elif "password" in t:
        return StateKind.PASSWORD_PROMPT
    elif "hardware monitor" in t or "fan" in t:
        return StateKind.HARDWARE_MONITOR
    elif "board explorer" in t:
        return StateKind.BOARD_EXPLORER
    elif "boot" in t and "menu" in t:
        return StateKind.BOOT_MENU
    elif "save" in t or "reset" in t or "reboot" in t:
        return StateKind.SAVE_CHANGES_MODAL
    return StateKind.SETTING_LIST

def normalize_bios_state(
    run_id: str,
    device_id: str,
    vlm_data: Dict[str, Any],
    screenshot_id: str,
    sha256: str,
    perceptual_hash: str,
    resolution: List[int],
    captured_at: str,
    ocr_confidence: float = 0.95,
    adapter: Optional["BiosAdapter"] = None,
) -> BiosState:
    """Combines raw inputs and VLM parses to yield a BiosState domain object."""
    state_id = "state_" + uuid.uuid4().hex[:12]

    # 1. Frame Metadata
    frame = FrameMetadata(
        screenshot_id=screenshot_id,
        sha256=sha256,
        perceptual_hash=perceptual_hash,
        resolution=resolution,
        captured_at=captured_at
    )

    # 2. Bios Metadata
    # Try to extract vendor from title or path
    title = vlm_data.get("screen_title") or ""
    vendor = "generic"
    board_hint = "unknown"
    family = "generic_uefi"

    if adapter:
        vendor = adapter.vendor
        if vendor == "msi":
            board_hint = "z690"
            family = "click_bios"
    else:
        if "msi" in title.lower() or "click bios" in title.lower():
            vendor = "msi"
            board_hint = "z690"
            family = "click_bios"

    bios = BiosMetadata(
        vendor=vendor,
        board_hint=board_hint,
        family=family,
        mode="advanced" if "ez" not in title.lower() else "ez"
    )

    # 3. Location Metadata
    menu_path = vlm_data.get("menu_path") or []
    top_module = menu_path[0] if menu_path else (adapter.identify_module(title) if adapter else "SETTINGS")
    screen_kind = parse_state_kind(title)

    location = LocationMetadata(
        screen_kind=screen_kind,
        top_module=top_module,
        breadcrumb=menu_path,
        screen_title=title if title else None
    )

    # 4. Control Entries
    controls: List[ControlEntry] = []
    selected_idx = vlm_data.get("cursor_at")
    vlm_entries = vlm_data.get("entries") or []

    selection_label = None
    selection_val = None
    selection_bbox = None

    for idx, e in enumerate(vlm_entries):
        cid = f"ctrl_{idx:03d}"
        label = e.get("label", "Unknown")
        val = e.get("value")
        # Treat numeric etc
        t = e.get("type", "unknown")

        role = ControlRole.UNKNOWN
        if t == "submenu":
            role = ControlRole.SUBMENU
        elif t in ("leaf-toggle", "leaf-numeric", "leaf-enum"):
            role = ControlRole.SETTING
        elif t == "leaf-info":
            role = ControlRole.INFO

        is_selected = (selected_idx is not None and idx == selected_idx)
        if adapter:
            label = adapter.normalize_label(label)

        # Risk classification
        risk_class = RiskClass.LOW
        lbl_l = label.lower()
        dw_list = adapter.hard_block_keywords if adapter and adapter.hard_block_keywords else DANGEROUS_WORDS
        if any(dw.lower() in lbl_l for dw in dw_list):
            risk_class = RiskClass.BLOCKED
        elif role == ControlRole.SETTING:
            risk_class = RiskClass.MEDIUM
            if "voltage" in lbl_l or "clock" in lbl_l or "multiplier" in lbl_l:
                risk_class = RiskClass.HIGH

        if is_selected:
            selection_label = label
            selection_val = val
            selection_bbox = e.get("bbox")

        controls.append(ControlEntry(
            control_id=cid,
            label=label,
            value=str(val) if val is not None else None,
            role=role,
            selected=is_selected,
            risk=risk_class,
            bbox=e.get("bbox"),
            options=e.get("options")
        ))

    # 5. Selection Metadata
    selection = SelectionMetadata(
        selected_index=selected_idx,
        label=selection_label,
        value=str(selection_val) if selection_val is not None else None,
        bbox=selection_bbox,
        confidence=vlm_data.get("confidence", 0.90)
    )

    # 6. Risk Status
    blocklist_flag = vlm_data.get("blocklist_flag", False)
    blocklist_keywords = vlm_data.get("blocklist_keywords") or []

    # Analyze screen elements for implicit blocklist
    for ctrl in controls:
        if ctrl.risk == RiskClass.BLOCKED:
            blocklist_flag = True
            if ctrl.label not in blocklist_keywords:
                blocklist_keywords.append(ctrl.label)

    hazards = []
    if screen_kind in (StateKind.FLASH_UTILITY, StateKind.SECURE_ERASE, StateKind.PASSWORD_PROMPT):
        hazards.append("destructive_screen")
        blocklist_flag = True

    risk = RiskStatus(
        blocklist_flag=blocklist_flag,
        blocklist_keywords=blocklist_keywords,
        hazards=hazards,
        policy_class="blocked" if blocklist_flag else "context_gated"
    )

    # 7. Action Policies
    # Pre-populate list of allowed keys based on danger
    safe = ["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Escape"]
    context_gated = ["Enter"]
    approval_required = ["F10"]
    blocked_actions = ["F6"] # defaults is unsafe in crawl

    if blocklist_flag:
        # Emergency exit
        safe = ["Escape"]
        context_gated = []
        approval_required = []
        blocked_actions = ["Enter", "F10", "F6"]

    actions = ActionPolicies(
        safe=safe,
        context_gated=context_gated,
        approval_required=approval_required,
        blocked=blocked_actions
    )

    # 8. Confidence
    confidence = ConfidenceMetrics(
        ocr=ocr_confidence,
        vlm=0.92,
        state=0.90
    )

    return BiosState(
        state_id=state_id,
        run_id=run_id,
        device_id=device_id,
        frame=frame,
        bios=bios,
        location=location,
        selection=selection,
        controls=controls,
        modal=ModalMetadata(present=False),
        risk=risk,
        actions=actions,
        confidence=confidence
    )
