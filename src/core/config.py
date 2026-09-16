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
    qdrant_location: str = Field(default=":memory:", description="Qdrant host or in-memory location")
    embedding_model: str = Field(default="BAAI/bge-m3", description="FastEmbed model name")
    ripgrep_path: str = Field(default="rg", description="Ripgrep binary path")

    # LLM Settings (if connected to provider)
    openai_api_key: Optional[str] = Field(default=None, description="OpenAI API Key")
    anthropic_api_key: Optional[str] = Field(default=None, description="Anthropic API Key")
    default_model: str = Field(default="gpt-4o", description="Default model for LangGraph agent")

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
                    # check type
                    ann = getattr(f_info, "annotation", getattr(f_info, "type_", str))
                    if ann is bool:
                        setattr(self, field_name, env_val.lower() in ("true", "1", "yes"))
                    elif ann is int:
                        setattr(self, field_name, int(env_val))
                    else:
                        setattr(self, field_name, env_val)


settings = Settings()
