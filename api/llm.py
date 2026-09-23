"""Small OpenAI-compatible client with provider fallback."""

import os
from typing import Any


class LLMUnavailable(RuntimeError):
    """Raised when no configured provider can answer."""


def provider_candidates() -> list[tuple[str, str, str]]:
    configured = os.getenv("LLM_PROVIDER", "").strip().lower()
    providers = [configured] if configured in {"openai", "nvidia"} else []
    providers += [item for item in ("openai", "nvidia") if item not in providers]
    result = []
    for provider in providers:
        key = os.getenv("OPENAI_API_KEY" if provider == "openai" else "NVIDIA_API_KEY", "").strip()
        if not key:
            continue
        base_url = "https://integrate.api.nvidia.com/v1" if provider == "nvidia" else None
        model = os.getenv("OPENAI_MODEL" if provider == "openai" else "NVIDIA_MODEL", "").strip()
        model = model or ("gpt-4o-mini" if provider == "openai" else "meta/llama-3.3-70b-instruct")
        result.append((provider, key, model))
    return result


def complete(messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None) -> Any:
    """Run one chat completion, trying the configured provider then fallback."""
    candidates = provider_candidates()
    if not candidates:
        raise LLMUnavailable("No LLM key is configured. Set OPENAI_API_KEY or NVIDIA_API_KEY.")
    try:
        from openai import OpenAI
    except ImportError as error:
        raise LLMUnavailable("Install the openai package to enable the assistant.") from error
    last_error: Exception | None = None
    for provider, key, model in candidates:
        try:
            kwargs: dict[str, Any] = {"api_key": key, "timeout": 30.0, "max_retries": 0}
            if provider == "nvidia":
                kwargs["base_url"] = "https://integrate.api.nvidia.com/v1"
            client = OpenAI(**kwargs)
            request: dict[str, Any] = {"model": model, "messages": messages}
            if tools:
                request.update({"tools": tools, "tool_choice": "auto"})
            return client.chat.completions.create(**request)
        except Exception as error:
            last_error = error
    raise LLMUnavailable(f"All configured LLM providers failed: {last_error}")
