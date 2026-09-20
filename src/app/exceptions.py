"""App shell domain exceptions."""

from __future__ import annotations

from typing import Any, Optional


class AppError(Exception):
    """Base application error with HTTP mapping metadata."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "APP_ERROR",
        status_code: int = 400,
        detail: Any = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.detail = detail


class NotFoundError(AppError):
    def __init__(self, message: str = "Not found", *, code: str = "NOT_FOUND", detail: Any = None):
        super().__init__(message, code=code, status_code=404, detail=detail)


class ConflictError(AppError):
    def __init__(self, message: str = "Conflict", *, code: str = "CONFLICT", detail: Any = None):
        super().__init__(message, code=code, status_code=409, detail=detail)


class WorkspaceBusyError(AppError):
    def __init__(self, message: str = "Workspace is currently indexing", *, detail: Any = None):
        super().__init__(message, code="WORKSPACE_INDEXING", status_code=409, detail=detail)


class ValidationAppError(AppError):
    def __init__(
        self,
        message: str = "Validation failed",
        *,
        code: str = "VALIDATION_ERROR",
        detail: Any = None,
    ):
        super().__init__(message, code=code, status_code=422, detail=detail)


class GuideFailedError(AppError):
    def __init__(self, message: str = "Guide generation failed", *, detail: Any = None):
        super().__init__(message, code="GUIDE_FAILED", status_code=502, detail=detail)
