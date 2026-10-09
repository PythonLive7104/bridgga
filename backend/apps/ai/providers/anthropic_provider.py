"""Anthropic provider.

Uses ``client.messages.parse`` with a Pydantic ``output_format``, so the API
constrains the response to the schema and the SDK hands back a validated
instance. That removes a whole class of failure the alternative invites:
asking for JSON in the prompt, then parsing a fenced code block by hand.

Prompt caching is applied to the stable prefix. Caching is a prefix match, so
the ordering here is deliberate: fixed instructions first, then the cacheable
context with the breakpoint on it, and the volatile per-request content last in
``messages`` where it cannot invalidate anything.

``thinking`` is deliberately not sent. Omitting it is correct on every model
this layer routes to: Opus 5.5 and Sonnet 5.5 run adaptive thinking by default
and reject ``{"type": "disabled"}`` outright, while Haiku 4.5 simply runs
without it.
"""

from __future__ import annotations

import time
from typing import Any

import structlog

from apps.ai.pricing import ModelSpec
from apps.ai.providers.base import (
    AIOutputInvalid,
    AIProvider,
    AIProviderError,
    AIProviderUnavailable,
    AIQuotaExhausted,
    AIRateLimited,
    AIRefused,
    CompletionRequest,
    CompletionResponse,
    TokenUsage,
)

logger = structlog.get_logger(__name__)

# Below this, a cache breakpoint cannot pay for itself -- the minimum cacheable
# prefix is model-dependent (512-4096 tokens) and a shorter one silently fails
# to cache while still costing the 1.25x write multiplier.
MIN_CACHEABLE_CHARS = 8_000


class AnthropicProvider(AIProvider):
    name = "anthropic"

    def __init__(self, api_key: str | None = None, *, client: Any = None) -> None:
        self._client = client
        self._api_key = api_key

    @property
    def client(self) -> Any:
        if self._client is None:
            import anthropic

            # No api_key argument when none was supplied: the SDK resolves
            # ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN or an `ant auth login`
            # profile on its own, and passing an explicit None breaks that.
            self._client = (
                anthropic.Anthropic(api_key=self._api_key)
                if self._api_key
                else anthropic.Anthropic()
            )
        return self._client

    def complete(self, request: CompletionRequest, *, spec: ModelSpec) -> CompletionResponse:
        import anthropic

        system = self._build_system(request)
        max_tokens = min(request.max_output_tokens, spec.max_output_tokens)
        started = time.monotonic()

        try:
            response = self.client.messages.parse(
                model=spec.model_id,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": request.user_content}],
                output_format=request.output_schema,
            )
        except anthropic.RateLimitError as exc:
            raise AIRateLimited(str(exc)) from exc
        except anthropic.APITimeoutError as exc:
            raise AIProviderUnavailable("The model took too long to respond") from exc
        except anthropic.APIConnectionError as exc:
            raise AIProviderUnavailable("Could not reach the model provider") from exc
        except anthropic.APIStatusError as exc:
            # Anthropic reports an empty balance as a 4xx carrying this
            # message, not as a 429 the way OpenAI does. Checked before the
            # generic branch because it is the one provider failure an
            # operator can actually fix -- see AIQuotaExhausted.
            if "credit balance" in str(exc).lower():
                raise AIQuotaExhausted(
                    "The Anthropic account has no credit remaining. Add credits to continue."
                ) from exc
            # 5xx is worth retrying; a 4xx is our bug and will fail identically.
            error: AIProviderError = (
                AIProviderUnavailable(f"Provider error {exc.status_code}")
                if exc.status_code >= 500
                else AIProviderError(f"Provider rejected the request: {exc.status_code}")
            )
            raise error from exc

        stop_reason = getattr(response, "stop_reason", "") or ""
        if stop_reason == "refusal":
            details = getattr(response, "stop_details", None)
            raise AIRefused(
                "The model declined this request.",
                category=getattr(details, "category", "") or "",
            )

        parsed = getattr(response, "parsed_output", None)
        if parsed is None:
            # Most often max_tokens cut the response off mid-object.
            raise AIOutputInvalid(
                f"Model returned no parseable output (stop_reason={stop_reason!r})"
            )

        usage = self._read_usage(response)
        latency_ms = round((time.monotonic() - started) * 1000, 2)

        if (
            usage.cache_read_tokens == 0
            and usage.cache_write_tokens == 0
            and system_is_cached(request)
        ):
            # Not fatal, but it means we are paying full price on every call.
            logger.debug("ai_cache_miss", model=spec.model_id)

        return CompletionResponse(
            parsed=parsed,
            raw_text=self._first_text(response),
            usage=usage,
            model_id=spec.model_id,
            stop_reason=stop_reason,
            latency_ms=latency_ms,
        )

    def count_tokens(self, request: CompletionRequest, *, spec: ModelSpec) -> int:
        """Real token count, for the pre-launch cost estimate in PRD section 36."""
        try:
            result = self.client.messages.count_tokens(
                model=spec.model_id,
                system=self._build_system(request),
                messages=[{"role": "user", "content": request.user_content}],
            )
            return int(result.input_tokens)
        except Exception:
            logger.debug("token_count_failed", model=spec.model_id, exc_info=True)
            return super().count_tokens(request, spec=spec)

    @staticmethod
    def _build_system(request: CompletionRequest) -> list[dict[str, Any]]:
        system: list[dict[str, Any]] = [{"type": "text", "text": request.instructions}]
        if request.cacheable_context:
            block: dict[str, Any] = {"type": "text", "text": request.cacheable_context}
            if system_is_cached(request):
                block["cache_control"] = {"type": "ephemeral"}
            system.append(block)
        return system

    @staticmethod
    def _read_usage(response: Any) -> TokenUsage:
        usage = getattr(response, "usage", None)
        if usage is None:
            return TokenUsage()
        return TokenUsage(
            input_tokens=getattr(usage, "input_tokens", 0) or 0,
            output_tokens=getattr(usage, "output_tokens", 0) or 0,
            cache_write_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
            cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
        )

    @staticmethod
    def _first_text(response: Any) -> str:
        for block in getattr(response, "content", []) or []:
            if getattr(block, "type", "") == "text":
                return getattr(block, "text", "") or ""
        return ""


def system_is_cached(request: CompletionRequest) -> bool:
    """Whether the context is long enough for a cache breakpoint to pay off."""
    return len(request.cacheable_context) >= MIN_CACHEABLE_CHARS
