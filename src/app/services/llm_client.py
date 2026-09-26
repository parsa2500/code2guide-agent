"""Shared OpenRouter / OpenAI chat completion helper."""

from __future__ import annotations

import os
from typing import Optional

from src.core.config import settings


def resolve_api_key() -> Optional[str]:
    return (
        settings.openrouter_api_key
        or os.getenv("OPENROUTER_API_KEY")
        or settings.openai_api_key
        or os.getenv("OPENAI_API_KEY")
        or None
    )


def resolve_model() -> str:
    return settings.openrouter_model or settings.default_model or "openrouter/free"


def resolve_base_url() -> str:
    return settings.openrouter_base_url or os.getenv(
        "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
    )


def chat_completion(
    *,
    system: str,
    user: str,
    temperature: float = 0.2,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> Optional[str]:
    """Non-streaming chat completion. Returns None if no key or clients unavailable."""
    key = api_key or resolve_api_key()
    if not key:
        return None
    model_name = model or resolve_model()
    base_url = resolve_base_url()

    try:
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import SystemMessage, HumanMessage

        llm = ChatOpenAI(
            model=model_name,
            api_key=key,
            base_url=base_url,
            temperature=temperature,
        )
        response = llm.invoke(
            [SystemMessage(content=system), HumanMessage(content=user)]
        )
        return str(response.content)
    except Exception:
        pass

    try:
        import openai

        client = openai.OpenAI(api_key=key, base_url=base_url)
        completion = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
        )
        return completion.choices[0].message.content
    except Exception:
        return None
