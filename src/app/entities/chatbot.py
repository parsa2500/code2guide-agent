"""Chatbot entity."""

from __future__ import annotations

from dataclasses import dataclass

from src.app.enums import ChatbotRole


@dataclass(slots=True)
class ChatbotEntity:
    id: str
    workspace_id: str
    name: str
    role: ChatbotRole
