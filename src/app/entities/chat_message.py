"""Chat message entity."""

from __future__ import annotations

from dataclasses import dataclass

from src.app.enums import ChatRole


@dataclass(slots=True)
class ChatMessageEntity:
    id: str
    workspace_id: str
    chatbot_id: str
    role: ChatRole
    text: str
    at: str
