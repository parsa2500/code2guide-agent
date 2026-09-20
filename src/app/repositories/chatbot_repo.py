"""Chatbot repository."""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.app.entities.chatbot import ChatbotEntity
from src.app.enums import ChatbotRole
from src.db.models.chatbot import Chatbot


def _to_entity(row: Chatbot) -> ChatbotEntity:
    return ChatbotEntity(
        id=row.id,
        workspace_id=row.workspace_id,
        name=row.name,
        role=ChatbotRole(row.role),
    )


class ChatbotRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_many(self, entities: List[ChatbotEntity]) -> List[ChatbotEntity]:
        rows = []
        for entity in entities:
            row = Chatbot(
                id=entity.id,
                workspace_id=entity.workspace_id,
                name=entity.name,
                role=entity.role.value,
            )
            self.db.add(row)
            rows.append(row)
        self.db.flush()
        return [_to_entity(r) for r in rows]

    def list_by_workspace(self, workspace_id: str) -> List[ChatbotEntity]:
        stmt = select(Chatbot).where(Chatbot.workspace_id == workspace_id).order_by(Chatbot.id)
        rows = list(self.db.scalars(stmt).all())
        return [_to_entity(r) for r in rows]

    def get(self, workspace_id: str, chatbot_id: str) -> Optional[ChatbotEntity]:
        stmt = select(Chatbot).where(
            Chatbot.workspace_id == workspace_id,
            Chatbot.id == chatbot_id,
        )
        row = self.db.scalars(stmt).first()
        return _to_entity(row) if row else None
