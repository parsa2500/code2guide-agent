"""Chat message repository."""

from __future__ import annotations

from typing import List, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.app.entities.chat_message import ChatMessageEntity
from src.app.enums import ChatRole
from src.db.models.chat_message import ChatMessage


def _to_entity(row: ChatMessage) -> ChatMessageEntity:
    return ChatMessageEntity(
        id=row.id,
        workspace_id=row.workspace_id,
        chatbot_id=row.chatbot_id,
        role=ChatRole(row.role),
        text=row.text,
        at=row.at,
    )


class ChatMessageRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, entity: ChatMessageEntity) -> ChatMessageEntity:
        row = ChatMessage(
            id=entity.id,
            workspace_id=entity.workspace_id,
            chatbot_id=entity.chatbot_id,
            role=entity.role.value,
            text=entity.text,
            at=entity.at,
        )
        self.db.add(row)
        self.db.flush()
        return _to_entity(row)

    def list_by_bot(
        self,
        workspace_id: str,
        chatbot_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[ChatMessageEntity], int]:
        filters = [
            ChatMessage.workspace_id == workspace_id,
            ChatMessage.chatbot_id == chatbot_id,
        ]
        total = int(
            self.db.scalar(select(func.count()).select_from(ChatMessage).where(*filters)) or 0
        )
        stmt = (
            select(ChatMessage)
            .where(*filters)
            .order_by(ChatMessage.at.asc())
            .limit(limit)
            .offset(offset)
        )
        rows = list(self.db.scalars(stmt).all())
        return [_to_entity(r) for r in rows], total
