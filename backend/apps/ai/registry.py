"""Provider selection.

Which vendor answers is a settings decision, not a code decision. Agents never
name a provider, so switching vendors is one environment variable.

Defaulting to the stub when no key is configured means the whole stack runs
locally and in CI without credentials -- and, more importantly, without a test
accidentally spending money.
"""

from __future__ import annotations

import functools
import os

import structlog
from django.conf import settings

from apps.ai.providers.base import AIProvider

logger = structlog.get_logger(__name__)

SUPPORTED_PROVIDERS = ("anthropic", "openai", "stub")


def _detect_provider() -> str:
    """Explicit setting wins; otherwise pick whichever key is present."""
    configured = (getattr(settings, "AI_PROVIDER", "") or "").strip().lower()
    if configured:
        return configured
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    return "stub"


def _build_provider() -> AIProvider:
    name = _detect_provider()

    if name == "anthropic":
        from apps.ai.providers.anthropic_provider import AnthropicProvider

        return AnthropicProvider()

    if name == "openai":
        from apps.ai.providers.openai_provider import OpenAIProvider

        return OpenAIProvider()

    if name == "stub":
        from apps.ai.providers.stub import StubProvider

        logger.info(
            "ai_provider_stubbed",
            reason="no ANTHROPIC_API_KEY or OPENAI_API_KEY, and no AI_PROVIDER set",
        )
        return StubProvider()

    raise ValueError(f"Unknown AI_PROVIDER {name!r}. Expected one of {SUPPORTED_PROVIDERS}.")


@functools.lru_cache(maxsize=1)
def _cached_provider() -> AIProvider:
    return _build_provider()


def get_provider() -> AIProvider:
    """The configured provider. Cached: SDK clients hold connection pools."""
    return _cached_provider()


def reset_provider_cache() -> None:
    """Drop the cached provider. For tests that change settings."""
    _cached_provider.cache_clear()
