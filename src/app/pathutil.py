"""Path normalization helpers."""

from __future__ import annotations

from pathlib import Path

from src.app.exceptions import ValidationAppError


def normalize_workspace_path(raw: str) -> str:
    """Strip and resolve path; reject empty."""
    text = (raw or "").strip()
    if not text:
        raise ValidationAppError("Path must not be empty", code="INVALID_PATH")
    try:
        return str(Path(text).expanduser().resolve())
    except OSError as exc:
        raise ValidationAppError(f"Invalid path: {exc}", code="INVALID_PATH") from exc
