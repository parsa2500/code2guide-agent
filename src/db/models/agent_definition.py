"""Agent definition ORM model (global registry)."""

from __future__ import annotations

from typing import TYPE_CHECKING, List

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base

if TYPE_CHECKING:
    from src.db.models.workspace_agent import WorkspaceAgent


class AgentDefinition(Base):
    __tablename__ = "agent_definitions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    policy_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reject_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    clarify_first: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    settings_schema: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(64), nullable=False)

    workspace_bindings: Mapped[List["WorkspaceAgent"]] = relationship(
        back_populates="agent",
        cascade="all, delete-orphan",
    )
