"""Prefixed ID generators."""

from __future__ import annotations

import secrets
import string

from src.app.constants import (
    ID_PREFIX_ACTIVITY_LOG,
    ID_PREFIX_GUIDE_MESSAGE,
    ID_PREFIX_GUIDE_SESSION,
    ID_PREFIX_MESSAGE,
    ID_PREFIX_UPDATE_JOB,
    ID_PREFIX_WORKSPACE,
)

_ALPHABET = string.ascii_lowercase + string.digits


def _suffix(length: int = 8) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))


def new_id(prefix: str) -> str:
    return f"{prefix}_{_suffix()}"


def new_workspace_id() -> str:
    return new_id(ID_PREFIX_WORKSPACE)


def new_update_job_id() -> str:
    return new_id(ID_PREFIX_UPDATE_JOB)


def new_activity_log_id() -> str:
    return new_id(ID_PREFIX_ACTIVITY_LOG)


def new_message_id() -> str:
    return new_id(ID_PREFIX_MESSAGE)


def new_guide_session_id() -> str:
    return new_id(ID_PREFIX_GUIDE_SESSION)


def new_guide_message_id() -> str:
    return new_id(ID_PREFIX_GUIDE_MESSAGE)
