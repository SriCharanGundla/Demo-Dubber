from __future__ import annotations

from dataclasses import dataclass

from demo_dubber.config import Settings
from demo_dubber.services.openai_cleanup import (
    OpenAICleanupService,
    OpenAICompatibleChatCleanupService,
)


@dataclass(frozen=True)
class CleanupProviderInfo:
    id: str
    label: str
    model: str
    configured: bool


def cleanup_provider_catalog(settings: Settings) -> list[CleanupProviderInfo]:
    return [
        CleanupProviderInfo(
            "openai", "OpenAI", settings.cleanup_model, bool(settings.openai_api_key)
        ),
        CleanupProviderInfo(
            "gemini",
            "Gemini AI Studio",
            settings.gemini_model,
            bool(settings.gemini_api_key),
        ),
        CleanupProviderInfo(
            "openrouter",
            "OpenRouter",
            settings.openrouter_model,
            bool(settings.openrouter_api_key),
        ),
    ]


def build_cleanup_service(settings: Settings, provider: str):
    provider_id = provider.strip().lower()
    if provider_id == "openai":
        return OpenAICleanupService(
            api_key=settings.openai_api_key,
            model=settings.cleanup_model,
        )
    if provider_id == "gemini":
        return OpenAICompatibleChatCleanupService(
            base_url=settings.gemini_base_url,
            token=settings.gemini_api_key,
            model=settings.gemini_model,
            provider_name="Gemini AI Studio",
            default_headers={"x-goog-api-client": "demo-dubber-oai/0.2.0"},
        )
    if provider_id == "openrouter":
        headers = {"X-OpenRouter-Title": settings.openrouter_app_name}
        if settings.openrouter_site_url:
            headers["HTTP-Referer"] = settings.openrouter_site_url
        return OpenAICompatibleChatCleanupService(
            base_url=settings.openrouter_base_url,
            token=settings.openrouter_api_key,
            model=settings.openrouter_model,
            provider_name="OpenRouter",
            default_headers=headers,
            require_structured_parameters=True,
        )
    raise ValueError(f"Unknown cleanup provider: {provider}")
