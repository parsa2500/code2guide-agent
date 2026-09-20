"""Chat DTOs."""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field

from src.app.enums import ChatRole, ChatbotRole


class ChatbotOut(BaseModel):
    id: str
    name: str
    role: ChatbotRole


class ChatbotListOut(BaseModel):
    items: List[ChatbotOut]


class ChatMessageOut(BaseModel):
    id: str
    role: ChatRole
    text: str
    at: str


class ChatMessageListOut(BaseModel):
    items: List[ChatMessageOut]
    total: int
    limit: int = 100
    offset: int = 0


class SendMessageIn(BaseModel):
    text: str = Field(..., min_length=1)


class SendMessageOut(BaseModel):
    user_message: ChatMessageOut
    assistant_message: ChatMessageOut
