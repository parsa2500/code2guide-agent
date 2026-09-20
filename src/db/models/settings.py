"""Workspace settings ORM model."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base

if TYPE_CHECKING:
    from src.db.models.workspace import Workspace


class WorkspaceSettings(Base):
    __tablename__ = "workspace_settings"

    workspace_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        primary_key=True,
    )
    default_agent: Mapped[str] = mapped_column(String(128), nullable=False, default="guide-agent")
    enabled_chatbots: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    audience_default: Mapped[str] = mapped_column(String(32), nullable=False, default="end_user")
    auto_index: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    mcp_enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    workspace: Mapped["Workspace"] = relationship(back_populates="setting")
