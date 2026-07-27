from __future__ import annotations

from typing import Any, List, Optional, Union

from pydantic import BaseModel, Field


class BiosEntry(BaseModel):
    label: str
    type: str = Field(
        description="submenu | leaf-toggle | leaf-numeric | leaf-enum | leaf-info | unknown"
    )
    value: Optional[Union[str, int, float]] = None
    options: Optional[List[str]] = None
    key_to_enter: str = "Enter"
    selected: bool = False
    bbox: Optional[List[float]] = Field(
        default=None, description="[x0, y0, x1, y1] pixel coordinates in the screenshot"
    )
    legible: bool = True


class HotkeyBinding(BaseModel):
    key: str
    action: str


class ModalParse(BaseModel):
    present: bool = False
    title: Optional[str] = None
    message: Optional[str] = None
    buttons: List[str] = Field(default_factory=list)
    focused_button: Optional[str] = None


class ScrollInfo(BaseModel):
    more_above: bool = False
    more_below: bool = False


class RiskParse(BaseModel):
    dangerous: bool = False
    reason: Optional[str] = None
    keywords_seen: List[str] = Field(default_factory=list)


class BiosScreenParse(BaseModel):
    screen_title: Optional[str] = None
    menu_path: Optional[List[str]] = None
    cursor_at: Optional[int] = None
    entries: List[BiosEntry] = Field(default_factory=list)
    blocklist_flag: bool = False
    blocklist_keywords: List[str] = Field(default_factory=list)
    # --- v2 additions (all optional: v1 parses still validate) ---
    screen_kind: Optional[str] = Field(
        default=None,
        description="StateKind value, e.g. setting_list | boot_menu | confirmation_modal",
    )
    layout: Optional[str] = Field(
        default=None, description="list | grid | tabs_with_list | dialog"
    )
    help_text: Optional[str] = None
    hotkeys: List[HotkeyBinding] = Field(default_factory=list)
    modal: Optional[ModalParse] = None
    scroll: Optional[ScrollInfo] = None
    risk: Optional[RiskParse] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class BiosParseResult(BaseModel):
    """Wrapper that holds both the parsed model and raw dict for backward compat."""

    parsed: BiosScreenParse
    raw: dict[str, Any]
