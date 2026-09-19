"""Configuration settings for Code2Guide Agent."""

import os
from typing import Optional
from pydantic import BaseModel, Field

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
    _has_pydantic_settings = True
except ImportError:
    BaseSettings = BaseModel
    SettingsConfigDict = None
    _has_pydantic_settings = False


class Settings(BaseSettings):
    """Application settings and configuration parameters."""

    app_name: str = Field(default="code2guide-agent", description="Application name")
    app_env: str = Field(default="development", description="Environment stage")
    debug: bool = Field(default=True, description="Debug mode flag")
    host: str = Field(default="0.0.0.0", description="API host")
    port: int = Field(default=8000, description="API port")

    # Target Codebase workspace
    target_workspace_path: str = Field(
        default="./sample_workspace",
        description="Path to the repository being analyzed"
    )

    # Search & Indexing
    qdrant_url: Optional[str] = Field(
        default="http://localhost:6333",
        description="Qdrant HTTP URL (Docker). Prefer over qdrant_location."
    )
    qdrant_location: Optional[str] = Field(
        default=None,
        description="Legacy Qdrant path or :memory: when qdrant_url is unset"
    )
    embedding_provider: str = Field(
        default="google",
        description="Embedding backend: google | fastembed"
    )
    embedding_model: str = Field(
        default="text-embedding-004",
        description="Embedding model name"
    )
    embedding_dim: int = Field(default=768, description="Embedding vector dimension")
    google_api_key: Optional[str] = Field(default=None, description="Google AI Studio API Key")
    ripgrep_path: str = Field(default="rg", description="Ripgrep binary path")
    index_storage_path: str = Field(
        default=".code2guide/index",
        description="Directory for per-workspace SQLite knowledge graph DBs",
    )
    ast_inspect_limit: int = Field(
        default=0,
        description=(
            "Max UI files to AST-inspect during /ask fallback when index is empty. "
            "0 means unlimited. Deep index path never uses this cap."
        ),
    )

    # OpenRouter LLM
    openrouter_api_key: Optional[str] = Field(default=None, description="OpenRouter API Key")
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        description="OpenRouter OpenAI-compatible base URL"
    )
    openrouter_model: str = Field(
        default="openrouter/free",
        description="Default OpenRouter chat model"
    )

    # Legacy LLM Settings
    openai_api_key: Optional[str] = Field(default=None, description="OpenAI API Key")
    anthropic_api_key: Optional[str] = Field(default=None, description="Anthropic API Key")
    default_model: str = Field(
        default="openrouter/free",
        description="Default chat model for LangGraph agent"
    )

    if _has_pydantic_settings:
        model_config = SettingsConfigDict(
            env_file=".env",
            env_file_encoding="utf-8",
            extra="ignore"
        )
    else:
        def __init__(self, **values):
            super().__init__(**values)
            fields = getattr(self.__class__, "model_fields", None) or getattr(self.__class__, "__fields__", {})
            for field_name, f_info in fields.items():
                env_val = os.getenv(field_name.upper())
                if env_val is not None:
                    ann = getattr(f_info, "annotation", getattr(f_info, "type_", str))
                    if ann is bool:
                        setattr(self, field_name, env_val.lower() in ("true", "1", "yes"))
                    elif ann is int:
                        setattr(self, field_name, int(env_val))
                    else:
                        setattr(self, field_name, env_val)


settings = Settings()
