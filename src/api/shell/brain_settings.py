"""Brain settings routes (Qdrant / embedding)."""

from __future__ import annotations

from fastapi import APIRouter

from src.api.schemas.agents import BrainSettingsOut, BrainSettingsUpdateIn
from src.app.services.brain_settings_service import get_brain_settings, update_brain_settings

router = APIRouter(tags=["Brain Settings"])


@router.get("/brain-settings", response_model=BrainSettingsOut)
def read_brain_settings() -> BrainSettingsOut:
    data = get_brain_settings()
    return BrainSettingsOut(**data)


@router.put("/brain-settings", response_model=BrainSettingsOut)
def put_brain_settings(body: BrainSettingsUpdateIn) -> BrainSettingsOut:
    payload = body.model_dump(exclude_unset=True)
    data = update_brain_settings(payload)
    return BrainSettingsOut(**data)
