"""Guide chat session DTOs."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from src.app.enums import ChatRole


class GuideSessionOut(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str


class GuideSessionListOut(BaseModel):
    items: List[GuideSessionOut]


class GuideStepOut(BaseModel):
    id: str
    phase: str
    title: str
    detail: str = ""


class GuideMessageOut(BaseModel):
    id: str
    role: ChatRole
    text: str
    at: str
    steps: Optional[List[Dict[str, Any]]] = None


class GuideMessageListOut(BaseModel):
    items: List[GuideMessageOut]
    total: int
    limit: int = 200
    offset: int = 0


class GuideSendMessageIn(BaseModel):
    text: str = Field(..., min_length=1)
