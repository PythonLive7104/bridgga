"""Provider selection.

Which vendor answers is a settings decision, not a code decision. Defaulting to
the stub when no API key is configured means the whole stack runs locally and in
CI without credentials -- and, more importantly, without a test accidentally
spending money.
"""

from __future__ import annotations

import functools
import os

import structlog
from django.conf import settings

from apps.ai.providers.base import AIProvider

logger = structlog.get_logger(__name__)


def _build_provider() -> AIProvider:
    name = (getattr(settings, "AI_PROVIDER", "") or "").strip().lower()

    if not name:
        # Auto-detect: use the real provider only when a key is actually
        # present, so a missing key is a stubbed run rather than a crash.
        name = "anthropic" if os.environ.get("ANTHROPIC_API_KEY") else "stub"

    if name == "anthropic":
        from apps.ai.providers.anthropic_provider import AnthropicProvider

        return AnthropicProvider()

    if name == "stub":
        from apps.ai.providers.stub import StubProvider

        logger.info("ai_provider_stubbed", reason="no ANTHROPIC_API_KEY or AI_PROVIDER=stub")
        return StubProvider()

    raise ValueError(f"Unknown AI_PROVIDER {name!r}. Expected 'anthropic' or 'stub'.")


@functools.lru_cache(maxsize=1)
def _cached_provider() -> AIProvider:
    return _build_provider()


def get_provider() -> AIProvider:
    """The configured provider. Cached: SDK clients hold connection pools."""
    return _cached_provider()


def reset_provider_cache() -> None:
    """Drop the cached provider. For tests that change settings."""
    _cached_provider.cache_clear()
