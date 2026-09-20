"""App shell enums."""

from enum import Enum


class WorkspaceStatus(str, Enum):
    IDLE = "idle"
    INDEXING = "indexing"
    READY = "ready"
    ERROR = "error"


class AudienceDefault(str, Enum):
    END_USER = "end_user"
    TECHNICAL = "technical"


class UpdateJobStatus(str, Enum):
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class UpdateScope(str, Enum):
    FULL = "full"
    INCREMENTAL = "incremental"


class LogLevel(str, Enum):
    INFO = "info"
    WARN = "warn"
    ERROR = "error"


class LogSource(str, Enum):
    SYSTEM = "system"
    INDEXER = "indexer"
    API = "api"
    CHAT = "chat"
    SETTINGS = "settings"


class ChatRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"


class ChatbotRole(str, Enum):
    END_USER = "end_user"
    TECHNICAL = "technical"
