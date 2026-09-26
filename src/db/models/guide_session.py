"""Guide chat session ORM model."""

from __future__ import annotations

from typing import TYPE_CHECKING, List

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base

if TYPE_CHECKING:
    from src.db.models.guide_message import GuideMessage
    from src.db.models.workspace import Workspace


class GuideSession(Base):
    __tablename__ = "guide_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="Session جدید")
    created_at: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(64), nullable=False)

    workspace: Mapped["Workspace"] = relationship(back_populates="guide_sessions")
    messages: Mapped[List["GuideMessage"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="GuideMessage.at",
    )
