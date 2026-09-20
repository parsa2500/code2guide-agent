"""Settings repository."""

from __future__ import annotations

import json
from typing import List, Optional

from sqlalchemy.orm import Session

from src.app.entities.settings import WorkspaceSettingsEntity
from src.app.enums import AudienceDefault
from src.db.models.settings import WorkspaceSettings


def _decode_bots(raw: str) -> List[str]:
    try:
        data = json.loads(raw or "[]")
        if isinstance(data, list):
            return [str(x) for x in data]
    except json.JSONDecodeError:
        pass
    return []


def _to_entity(row: WorkspaceSettings) -> WorkspaceSettingsEntity:
    return WorkspaceSettingsEntity(
        workspace_id=row.workspace_id,
        default_agent=row.default_agent,
        enabled_chatbots=_decode_bots(row.enabled_chatbots),
        audience_default=AudienceDefault(row.audience_default),
        auto_index=bool(row.auto_index),
        mcp_enabled=bool(row.mcp_enabled),
    )


class SettingsRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, workspace_id: str) -> Optional[WorkspaceSettingsEntity]:
        row = self.db.get(WorkspaceSettings, workspace_id)
        return _to_entity(row) if row else None

    def upsert(self, entity: WorkspaceSettingsEntity) -> WorkspaceSettingsEntity:
        row = self.db.get(WorkspaceSettings, entity.workspace_id)
        payload = {
            "default_agent": entity.default_agent,
            "enabled_chatbots": json.dumps(entity.enabled_chatbots, ensure_ascii=False),
            "audience_default": entity.audience_default.value,
            "auto_index": 1 if entity.auto_index else 0,
            "mcp_enabled": 1 if entity.mcp_enabled else 0,
        }
        if row is None:
            row = WorkspaceSettings(workspace_id=entity.workspace_id, **payload)
            self.db.add(row)
        else:
            for key, value in payload.items():
                setattr(row, key, value)
        self.db.flush()
        return _to_entity(row)
