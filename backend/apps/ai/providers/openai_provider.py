"""OpenAI provider.

Uses the Responses API with ``client.responses.parse`` and a Pydantic
``text_format``, so the model is constrained to the schema and the SDK returns a
validated instance -- the same contract the Anthropic provider offers, which is
what lets agents switch vendors without changing.

Two vendor differences are normalised here rather than leaked upward:

* **Cached tokens are counted differently.** OpenAI reports ``input_tokens``
  *inclusive* of cached tokens, whereas Anthropic reports them separately.
  Passing OpenAI's figure straight through would bill every cache hit at full
  input price, so the cached count is subtracted before the usage object is
  built.
* **Caching is automatic, not annotated.** There is no cache-breakpoint
  concept; OpenAI caches long prefixes on its own. ``prompt_cache_key`` is sent
  so repeated calls for the same prompt route to the same cache.
"""

from __future__ import annotations

import hashlib
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

#: Markers OpenAI uses for "out of credit" rather than "too many requests".
#: Matched on the error body's type and code, with the message as a fallback
#: because the first two have been renamed before.
_QUOTA_MARKERS = ("insufficient_quota", "credit_balance_exhausted", "billing_hard_limit_reached")


def _is_quota_error(exc: Any) -> bool:
    body = getattr(exc, "body", None) or {}
    if isinstance(body, dict):
        error = body.get("error") if isinstance(body.get("error"), dict) else body
        fields = (error or {}).get("type", ""), (error or {}).get("code", "")
        if any(str(field) in _QUOTA_MARKERS for field in fields):
            return True
    text = str(exc).lower()
    return any(marker in text for marker in _QUOTA_MARKERS) or "no credits remaining" in text


class OpenAIProvider(AIProvider):
    name = "openai"

    def __init__(self, api_key: str | None = None, *, client: Any = None) -> None:
        self._client = client
        self._api_key = api_key

    @property
    def client(self) -> Any:
        if self._client is None:
            import openai

            # No api_key argument when none was supplied, so the SDK can
            # resolve OPENAI_API_KEY itself.
            self._client = (
                openai.OpenAI(api_key=self._api_key) if self._api_key else openai.OpenAI()
            )
        return self._client

    def complete(self, request: CompletionRequest, *, spec: ModelSpec) -> CompletionResponse:
        import openai

        instructions = self._build_instructions(request)
        max_output_tokens = min(request.max_output_tokens, spec.max_output_tokens)
        started = time.monotonic()

        try:
            response = self.client.responses.parse(
                model=spec.model_id,
                instructions=instructions,
                input=request.user_content,
                text_format=request.output_schema,
                max_output_tokens=max_output_tokens,
                # Groups requests sharing a prefix so they hit the same cache.
                # Derived from the instructions, which are the stable part.
                prompt_cache_key=self._cache_key(instructions),
            )
        except openai.RateLimitError as exc:
            # 429 covers two different problems. `insufficient_quota` means
            # the account has no credit left, and no amount of backoff will
            # change that -- see AIQuotaExhausted.
            if _is_quota_error(exc):
                raise AIQuotaExhausted(
                    "The OpenAI account has no credit remaining. Add credits to continue."
                ) from exc
            raise AIRateLimited(str(exc)) from exc
        except openai.APITimeoutError as exc:
            raise AIProviderUnavailable("The model took too long to respond") from exc
        except openai.APIConnectionError as exc:
            raise AIProviderUnavailable("Could not reach the model provider") from exc
        except openai.APIStatusError as exc:
            status = getattr(exc, "status_code", 500)
            error: AIProviderError = (
                AIProviderUnavailable(f"Provider error {status}")
                if status >= 500
                else AIProviderError(f"Provider rejected the request: {status}")
            )
            raise error from exc

        self._raise_for_incomplete(response)

        parsed = getattr(response, "output_parsed", None)
        if parsed is None:
            raise AIOutputInvalid(
                f"Model returned no parseable output (status={getattr(response, 'status', '')!r})"
            )

        return CompletionResponse(
            parsed=parsed,
            raw_text=getattr(response, "output_text", "") or "",
            usage=self._read_usage(response),
            model_id=spec.model_id,
            stop_reason=str(getattr(response, "status", "") or ""),
            latency_ms=round((time.monotonic() - started) * 1000, 2),
        )

    def count_tokens(self, request: CompletionRequest, *, spec: ModelSpec) -> int:
        """Character heuristic.

        The Responses API has no standalone token-counting endpoint, so the
        pre-launch estimate in PRD section 36 is approximate on this provider.
        It is labelled an estimate in the UI for exactly this reason.
        """
        return super().count_tokens(request, spec=spec)

    @staticmethod
    def _build_instructions(request: CompletionRequest) -> str:
        """Stable content first so OpenAI's automatic prefix caching can hit.

        Caching is a prefix match at both vendors even though only one of them
        asks you to mark it, so the ordering matters just as much here.
        """
        if request.cacheable_context:
            return f"{request.instructions}\n\n{request.cacheable_context}"
        return request.instructions

    @staticmethod
    def _cache_key(instructions: str) -> str:
        return hashlib.sha256(instructions.encode("utf-8")).hexdigest()[:32]

    @staticmethod
    def _raise_for_incomplete(response: Any) -> None:
        status = getattr(response, "status", "")

        if status == "incomplete":
            details = getattr(response, "incomplete_details", None)
            reason = getattr(details, "reason", "") or "unknown"
            # Truncated output is a schema failure in practice: the JSON is cut
            # off mid-object. Retryable, so the runner gets another attempt.
            raise AIOutputInvalid(f"Response was incomplete ({reason})")

        error = getattr(response, "error", None)
        if error is not None:
            code = getattr(error, "code", "") or ""
            message = getattr(error, "message", "") or "Model returned an error"
            if "refus" in code.lower() or "content_filter" in code.lower():
                raise AIRefused(message, category=code)
            raise AIProviderError(message)

        # A refusal can also arrive as a refusal content part rather than a
        # top-level error.
        for item in getattr(response, "output", []) or []:
            for part in getattr(item, "content", []) or []:
                if getattr(part, "type", "") == "refusal":
                    raise AIRefused(
                        getattr(part, "refusal", "") or "The model declined this request.",
                        category="refusal",
                    )

    @staticmethod
    def _read_usage(response: Any) -> TokenUsage:
        usage = getattr(response, "usage", None)
        if usage is None:
            return TokenUsage()

        details = getattr(usage, "input_tokens_details", None)
        cached = int(getattr(details, "cached_tokens", 0) or 0)
        cache_written = int(getattr(details, "cache_write_tokens", 0) or 0)

        total_input = int(getattr(usage, "input_tokens", 0) or 0)
        # OpenAI's input_tokens includes the cached portion. Subtract it so the
        # shared cost maths prices fresh and cached input separately, and never
        # below zero if the vendor ever changes this.
        fresh_input = max(total_input - cached, 0)

        return TokenUsage(
            input_tokens=fresh_input,
            output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
            cache_read_tokens=cached,
            cache_write_tokens=cache_written,
        )
