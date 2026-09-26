"""Guide chat message entity."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.app.enums import ChatRole


@dataclass(slots=True)
class GuideMessageEntity:
    id: str
    session_id: str
    workspace_id: str
    role: ChatRole
    text: str
    at: str
    steps: Optional[List[Dict[str, Any]]] = field(default=None)
