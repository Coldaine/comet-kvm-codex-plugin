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
    # v2: the VLM classifies the screen directly; the title heuristic is the fallback.
    # The heuristic is computed unconditionally so risk can union both (below):
    # VLM input only ever restricts, so it must never be able to hide a
    # destructive screen the title alone would have flagged.
    heuristic_kind = parse_state_kind(title)
    try:
        screen_kind = StateKind(vlm_data.get("screen_kind") or "")
    except ValueError:
        screen_kind = heuristic_kind

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

        is_selected = bool(e.get("selected")) or (selected_idx is not None and idx == selected_idx)
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
            options=e.get("options"),
            legible=e.get("legible", True) is not False,
        ))

    # 5. Selection Metadata
    vlm_confidence = vlm_data.get("confidence")
    selection = SelectionMetadata(
        selected_index=selected_idx,
        label=selection_label,
        value=str(selection_val) if selection_val is not None else None,
        bbox=selection_bbox,
        confidence=vlm_confidence if vlm_confidence is not None else 0.90
    )

    # 6. Risk Status
    # Scoped blocking: dangerous keywords visible in ambient chrome (e.g. the
    # persistent M-FLASH sidebar tile on every Click BIOS 5 screen) must not
    # block the whole screen, or the crawler can never descend anywhere. The
    # screen is blocked only when the danger is where we ARE (destructive
    # screen kind, or a keyword in the title/breadcrumb/modal) or what we
    # would ACTUATE next (the focused control). Dangerous controls elsewhere
    # on screen keep their per-control BLOCKED risk, which gates Enter on
    # them individually.
    blocklist_keywords = list(vlm_data.get("blocklist_keywords") or [])

    selected_blocked = False
    for ctrl in controls:
        if ctrl.risk == RiskClass.BLOCKED:
            if ctrl.label not in blocklist_keywords:
                blocklist_keywords.append(ctrl.label)
            if ctrl.selected:
                selected_blocked = True

    hazards = []
    # Union, not substitution: a wrong-but-valid VLM screen_kind (e.g. "setting_list"
    # on a screen titled "Secure Erase") must not suppress the title heuristic's hazard.
    destructive_kinds = (StateKind.FLASH_UTILITY, StateKind.SECURE_ERASE, StateKind.PASSWORD_PROMPT)
    screen_destructive = screen_kind in destructive_kinds or heuristic_kind in destructive_kinds
    if screen_destructive:
        hazards.append("destructive_screen")

    # VLM semantic risk still only ever restricts, but its keywords must name
    # where we are or what is focused — not ambient text elsewhere in the frame.
    risk_reason = None
    vlm_scoped_hit = False
    vlm_risk = vlm_data.get("risk") or {}
    vlm_modal_raw = vlm_data.get("modal") or {}
    if vlm_risk.get("dangerous"):
        hazards.append("vlm_semantic")
        risk_reason = vlm_risk.get("reason")
        scope_text = " ".join(
            str(part)
            for part in (
                title,
                *menu_path,
                selection_label,
                vlm_modal_raw.get("title"),
                vlm_modal_raw.get("message"),
            )
            if part
        ).lower()
        for kw in vlm_risk.get("keywords_seen") or []:
            if kw not in blocklist_keywords:
                blocklist_keywords.append(kw)
            if kw.lower() in scope_text:
                vlm_scoped_hit = True

    blocklist_flag = screen_destructive or selected_blocked or vlm_scoped_hit

    risk = RiskStatus(
        blocklist_flag=blocklist_flag,
        blocklist_keywords=blocklist_keywords,
        hazards=hazards,
        policy_class="blocked" if blocklist_flag else "context_gated",
        reason=risk_reason,
    )

    # 6b. Modal state (v2)
    vlm_modal = vlm_data.get("modal") or {}
    modal = ModalMetadata(
        present=bool(vlm_modal.get("present")),
        type="dialog" if vlm_modal.get("present") else None,
        message=vlm_modal.get("message"),
        options=list(vlm_modal.get("buttons") or []),
        title=vlm_modal.get("title"),
        focused=vlm_modal.get("focused_button"),
    )

    # 7. Action Policies
    # Pre-populate list of allowed keys based on danger
    safe = ["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Escape"]
    context_gated = ["Enter"]
    approval_required = ["F10"]
    blocked_actions = ["F6"] # defaults is unsafe in crawl

    if screen_destructive or vlm_scoped_hit or modal.present:
        # Emergency exit; a modal's Enter can confirm a save dialog.
        safe = ["Escape"]
        context_gated = []
        approval_required = []
        blocked_actions = ["Enter", "F10", "F6"]
    elif selected_blocked:
        # Sitting ON a dangerous tile: allow moving off it, never into it.
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
        vlm=vlm_confidence if vlm_confidence is not None else 0.92,
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
        modal=modal,
        risk=risk,
        actions=actions,
        confidence=confidence,
        layout=vlm_data.get("layout") or "list",
        help_text=vlm_data.get("help_text"),
        hotkeys=[dict(h) for h in (vlm_data.get("hotkeys") or [])],
        scroll=dict(vlm_data.get("scroll") or {}),
    )
