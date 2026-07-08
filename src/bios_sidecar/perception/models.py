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


class BiosScreenParse(BaseModel):
    screen_title: Optional[str] = None
    menu_path: Optional[List[str]] = None
    cursor_at: Optional[int] = None
    entries: List[BiosEntry] = Field(default_factory=list)
    blocklist_flag: bool = False
    blocklist_keywords: List[str] = Field(default_factory=list)


class BiosParseResult(BaseModel):
    """Wrapper that holds both the parsed model and raw dict for backward compat."""

    parsed: BiosScreenParse
    raw: dict[str, Any]
