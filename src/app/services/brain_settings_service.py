"""Brain settings read/write (in-memory + data/brain_settings.json)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from src.app.constants import BRAIN_SETTINGS_PATH
from src.core.config import settings

_BRAIN_KEYS = (
    "qdrant_url",
    "qdrant_location",
    "embedding_provider",
    "embedding_model",
    "embedding_dim",
)


def _settings_file() -> Path:
    path = Path(BRAIN_SETTINGS_PATH)
    if not path.is_absolute():
        # Resolve relative to repo root (parent of src/)
        repo_root = Path(__file__).resolve().parents[3]
        path = repo_root / path
    return path


def get_brain_settings() -> Dict[str, Any]:
    """Return current brain settings from in-memory config (after any JSON overlay)."""
    return {
        "qdrant_url": settings.qdrant_url,
        "qdrant_location": settings.qdrant_location,
        "embedding_provider": settings.embedding_provider,
        "embedding_model": settings.embedding_model,
        "embedding_dim": settings.embedding_dim,
        "persistence": str(_settings_file()),
    }


def load_brain_settings_file() -> None:
    """Apply persisted JSON onto in-memory settings if the file exists."""
    path = _settings_file()
    if not path.is_file():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(data, dict):
        return
    for key in _BRAIN_KEYS:
        if key in data and data[key] is not None:
            setattr(settings, key, data[key])


def update_brain_settings(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Update allowed brain fields in-memory and persist to data/brain_settings.json."""
    updates: Dict[str, Any] = {}
    for key in _BRAIN_KEYS:
        if key in payload:
            updates[key] = payload[key]
            setattr(settings, key, payload[key])

    path = _settings_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: Dict[str, Any] = {}
    if path.is_file():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(existing, dict):
                existing = {}
        except (OSError, json.JSONDecodeError):
            existing = {}
    existing.update(updates)
    # Always snapshot current effective values for the known keys
    for key in _BRAIN_KEYS:
        existing[key] = getattr(settings, key)
    path.write_text(json.dumps(existing, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return get_brain_settings()
