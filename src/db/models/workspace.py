"""Workspace ORM model."""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base

if TYPE_CHECKING:
    from src.db.models.activity_log import ActivityLog
    from src.db.models.chatbot import Chatbot
    from src.db.models.settings import WorkspaceSettings
    from src.db.models.update_job import UpdateJob


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="idle")
    created_at: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(64), nullable=False)
    deleted_at: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    setting: Mapped[Optional["WorkspaceSettings"]] = relationship(
        back_populates="workspace",
        uselist=False,
        cascade="all, delete-orphan",
    )
    update_jobs: Mapped[List["UpdateJob"]] = relationship(
        back_populates="workspace",
        cascade="all, delete-orphan",
    )
    activity_logs: Mapped[List["ActivityLog"]] = relationship(
        back_populates="workspace",
        cascade="all, delete-orphan",
    )
    chatbots: Mapped[List["Chatbot"]] = relationship(
        back_populates="workspace",
        cascade="all, delete-orphan",
    )
