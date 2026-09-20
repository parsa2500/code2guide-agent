"""Chatbot ORM model."""

from __future__ import annotations

from typing import TYPE_CHECKING, List

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base

if TYPE_CHECKING:
    from src.db.models.chat_message import ChatMessage
    from src.db.models.workspace import Workspace


class Chatbot(Base):
    __tablename__ = "chatbots"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        primary_key=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)

    workspace: Mapped["Workspace"] = relationship(back_populates="chatbots")
    messages: Mapped[List["ChatMessage"]] = relationship(
        back_populates="chatbot",
        cascade="all, delete-orphan",
        primaryjoin="and_(Chatbot.workspace_id==ChatMessage.workspace_id, Chatbot.id==ChatMessage.chatbot_id)",
        foreign_keys="[ChatMessage.workspace_id, ChatMessage.chatbot_id]",
    )
