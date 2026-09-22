"""Workspace ↔ agent binding ORM model."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base

if TYPE_CHECKING:
    from src.db.models.agent_definition import AgentDefinition
    from src.db.models.workspace import Workspace


class WorkspaceAgent(Base):
    __tablename__ = "workspace_agents"

    workspace_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        primary_key=True,
    )
    agent_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("agent_definitions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    overrides: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    # Minimal chat history counter for clarify_first gating (slice-1)
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    workspace: Mapped["Workspace"] = relationship(back_populates="agents")
    agent: Mapped["AgentDefinition"] = relationship(back_populates="workspace_bindings")
