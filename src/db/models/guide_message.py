"""Guide chat message ORM model."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base

if TYPE_CHECKING:
    from src.db.models.guide_session import GuideSession


class GuideMessage(Base):
    __tablename__ = "guide_messages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("guide_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    steps_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    at: Mapped[str] = mapped_column(String(64), nullable=False)

    session: Mapped["GuideSession"] = relationship(back_populates="messages")
