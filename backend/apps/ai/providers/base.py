"""Provider abstraction (PRD section 56).

The point of this layer is that agent code never imports a vendor SDK. An agent
asks for a tier and a schema; which model answers, and from which vendor, is a
configuration decision made in one place.

Deliberately narrow: one structured, non-streaming completion. Streaming,
tool use and multi-turn conversation are not here because nothing in Phase 2
needs them, and a protocol invented ahead of its callers ends up wrong.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, TypeVar

from pydantic import BaseModel

from apps.ai.pricing import ModelSpec

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class AIProviderError(RuntimeError):
    """Base class for provider failures."""

    retryable = False


class AIRateLimited(AIProviderError):
    retryable = True


class AIQuotaExhausted(AIProviderError):
    """The account is out of credit, as distinct from being rate limited.

    Both arrive as HTTP 429 from OpenAI, which is why this exists: waiting and
    trying again fixes a rate limit and cannot fix an empty balance. Treating
    the second as the first means every queued job retries, every retry fails
    the same way, and the operator reads "rate limited" in the logs while the
    actual problem is a billing page.

    Not retryable, and the message is written to be shown to a human: this is
    one of the few provider failures a customer can do something about.
    """

    retryable = False


class AIProviderUnavailable(AIProviderError):
    retryable = True


class AIOutputInvalid(AIProviderError):
    """The model answered, but not in the shape the caller requires.

    Retryable: a schema violation is usually a one-off, and the runner retries
    once with the validation error fed back before giving up.
    """

    retryable = True


class AIRefused(AIProviderError):
    """The model declined the request. Not retryable -- retrying is the same ask."""

    retryable = False

    def __init__(self, message: str, category: str = "") -> None:
        super().__init__(message)
        self.category = category


@dataclass(slots=True)
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_write_tokens
            + self.cache_read_tokens
        )

    def cost_micro_usd(self, spec: ModelSpec) -> int:
        return spec.cost_micro_usd(
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            cache_write_tokens=self.cache_write_tokens,
            cache_read_tokens=self.cache_read_tokens,
        )


@dataclass(slots=True)
class CompletionRequest:
    """One structured completion.

    ``cacheable_context`` is kept separate from ``instructions`` because prompt
    caching is a prefix match: stable content has to come first and volatile
    content last, or nothing ever caches. Callers would get that ordering wrong
    if the provider accepted a single blob.
    """

    instructions: str
    user_content: str
    output_schema: type[BaseModel]
    cacheable_context: str = ""
    max_output_tokens: int = 8_000
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CompletionResponse:
    parsed: BaseModel
    raw_text: str
    usage: TokenUsage
    model_id: str
    stop_reason: str = ""
    latency_ms: float = 0.0


class AIProvider(abc.ABC):
    """A vendor that can return a schema-valid structured completion."""

    name: str = "base"

    @abc.abstractmethod
    def complete(self, request: CompletionRequest, *, spec: ModelSpec) -> CompletionResponse:
        """Run one completion, or raise an ``AIProviderError`` subclass."""

    def count_tokens(self, request: CompletionRequest, *, spec: ModelSpec) -> int:
        """Estimated input tokens, for pre-flight cost estimates.

        The default is a rough character heuristic. Providers that expose a
        real counting endpoint should override it -- PRD section 36 requires a
        cost estimate before a campaign launches, and that number is shown to
        a paying customer.
        """
        characters = (
            len(request.instructions) + len(request.cacheable_context) + len(request.user_content)
        )
        return characters // 4
