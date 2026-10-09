"""OpenAI provider (PRD section 56).

Run against a fake client, so the suite never needs a key and never spends
money. What is asserted here is the adapter's contract: that it returns the
same shape the Anthropic provider does, and that it normalises the two places
the vendors genuinely differ.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel

from apps.ai.pricing import MODELS, Tier, resolve_model
from apps.ai.providers.base import (
    AIOutputInvalid,
    AIProviderError,
    AIQuotaExhausted,
    AIRateLimited,
    AIRefused,
    CompletionRequest,
)
from apps.ai.providers.openai_provider import OpenAIProvider

pytestmark = pytest.mark.security


class Answer(BaseModel):
    model_config = {"extra": "forbid"}
    answer: str


def make_request(**overrides: Any) -> CompletionRequest:
    defaults: dict[str, Any] = {
        "instructions": "Be accurate.",
        "user_content": "What is 2 + 2?",
        "output_schema": Answer,
    }
    defaults.update(overrides)
    return CompletionRequest(**defaults)


def fake_usage(
    *, input_tokens: int, output_tokens: int, cached: int = 0, written: int = 0
) -> SimpleNamespace:
    return SimpleNamespace(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
        input_tokens_details=SimpleNamespace(cached_tokens=cached, cache_write_tokens=written),
    )


class FakeResponses:
    def __init__(self, response: Any = None, error: Exception | None = None) -> None:
        self._response = response
        self._error = error
        self.calls: list[dict[str, Any]] = []

    def parse(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return self._response


class FakeClient:
    def __init__(self, responses: FakeResponses) -> None:
        self.responses = responses


def provider_with(response: Any = None, error: Exception | None = None) -> OpenAIProvider:
    return OpenAIProvider(client=FakeClient(FakeResponses(response, error)))


OPENAI_SPEC = MODELS["gpt-5-mini"]


# --------------------------------------------------------------------------- #
# Routing
# --------------------------------------------------------------------------- #


def test_openai_tiers_resolve_to_openai_models() -> None:
    for tier in Tier:
        spec = resolve_model(tier, provider="openai")
        assert spec.provider == "openai"


def test_openai_routing_is_cheapest_first() -> None:
    cheap = resolve_model(Tier.CHEAP, provider="openai")
    advanced = resolve_model(Tier.ADVANCED, provider="openai")
    assert cheap.input_micro_usd_per_mtok < advanced.input_micro_usd_per_mtok


def test_switching_provider_switches_the_whole_catalogue(settings: Any) -> None:
    """An agent names a tier, never a vendor, so this is the only switch needed."""
    settings.AI_MODEL_TIERS = {}
    settings.AI_PROVIDER = "openai"
    assert resolve_model(Tier.ADVANCED).provider == "openai"
    settings.AI_PROVIDER = "anthropic"
    assert resolve_model(Tier.ADVANCED).provider == "anthropic"


# --------------------------------------------------------------------------- #
# Success path
# --------------------------------------------------------------------------- #


def test_successful_completion_returns_parsed_output() -> None:
    response = SimpleNamespace(
        output_parsed=Answer(answer="4"),
        output_text='{"answer":"4"}',
        status="completed",
        error=None,
        incomplete_details=None,
        output=[],
        usage=fake_usage(input_tokens=100, output_tokens=5),
    )
    provider = provider_with(response)

    result = provider.complete(make_request(), spec=OPENAI_SPEC)

    assert result.parsed.answer == "4"
    assert result.model_id == "gpt-5-mini"
    assert result.usage.output_tokens == 5


def test_cached_tokens_are_not_double_counted() -> None:
    """OpenAI reports input_tokens inclusive of cached tokens.

    Passing that figure straight through would bill a cache hit at full input
    price -- ten times its real cost.
    """
    response = SimpleNamespace(
        output_parsed=Answer(answer="4"),
        output_text="",
        status="completed",
        error=None,
        incomplete_details=None,
        output=[],
        usage=fake_usage(input_tokens=10_000, output_tokens=100, cached=8_000),
    )

    usage = provider_with(response).complete(make_request(), spec=OPENAI_SPEC).usage

    assert usage.input_tokens == 2_000  # fresh only
    assert usage.cache_read_tokens == 8_000
    # Total still reconciles with what the vendor reported.
    assert usage.input_tokens + usage.cache_read_tokens == 10_000


def test_cached_call_costs_less_than_an_uncached_one() -> None:
    """The end-to-end consequence of the normalisation above."""
    base = {
        "output_parsed": Answer(answer="4"),
        "output_text": "",
        "status": "completed",
        "error": None,
        "incomplete_details": None,
        "output": [],
    }
    uncached = SimpleNamespace(**base, usage=fake_usage(input_tokens=10_000, output_tokens=100))
    cached = SimpleNamespace(
        **base, usage=fake_usage(input_tokens=10_000, output_tokens=100, cached=9_000)
    )

    cost_uncached = (
        provider_with(uncached).complete(make_request(), spec=OPENAI_SPEC).usage
    ).cost_micro_usd(OPENAI_SPEC)
    cost_cached = (
        provider_with(cached).complete(make_request(), spec=OPENAI_SPEC).usage
    ).cost_micro_usd(OPENAI_SPEC)

    assert cost_cached < cost_uncached


def test_stable_prefix_is_sent_first_and_keyed_for_caching() -> None:
    """Caching is a prefix match here too, even though it is automatic."""
    response = SimpleNamespace(
        output_parsed=Answer(answer="4"),
        output_text="",
        status="completed",
        error=None,
        incomplete_details=None,
        output=[],
        usage=fake_usage(input_tokens=10, output_tokens=1),
    )
    provider = provider_with(response)
    provider.complete(
        make_request(cacheable_context="LARGE STABLE CONTEXT", user_content="volatile"),
        spec=OPENAI_SPEC,
    )

    call = provider.client.responses.calls[0]
    assert call["instructions"].startswith("Be accurate.")
    assert "LARGE STABLE CONTEXT" in call["instructions"]
    # Volatile content stays out of the cached prefix.
    assert "volatile" not in call["instructions"]
    assert call["input"] == "volatile"
    assert call["prompt_cache_key"]


# --------------------------------------------------------------------------- #
# Failure mapping
# --------------------------------------------------------------------------- #


def test_truncated_response_is_retryable_not_silent() -> None:
    """An incomplete response is cut-off JSON, not a valid answer."""
    response = SimpleNamespace(
        output_parsed=None,
        output_text="",
        status="incomplete",
        error=None,
        incomplete_details=SimpleNamespace(reason="max_output_tokens"),
        output=[],
        usage=fake_usage(input_tokens=10, output_tokens=1),
    )

    with pytest.raises(AIOutputInvalid) as caught:
        provider_with(response).complete(make_request(), spec=OPENAI_SPEC)
    assert caught.value.retryable is True
    assert "max_output_tokens" in str(caught.value)


def test_refusal_content_part_is_surfaced_as_a_refusal() -> None:
    response = SimpleNamespace(
        output_parsed=None,
        output_text="",
        status="completed",
        error=None,
        incomplete_details=None,
        output=[
            SimpleNamespace(
                content=[SimpleNamespace(type="refusal", refusal="I can't help with that.")]
            )
        ],
        usage=fake_usage(input_tokens=10, output_tokens=1),
    )

    with pytest.raises(AIRefused) as caught:
        provider_with(response).complete(make_request(), spec=OPENAI_SPEC)
    # Not retryable: re-asking is the same question.
    assert caught.value.retryable is False


def _http_response(status: int) -> Any:
    """A real httpx2 response.

    The SDK's exception classes read response.request, so a stand-in namespace
    is not enough to construct one.
    """
    import httpx2

    request = httpx2.Request("POST", "https://api.openai.com/v1/responses")
    return httpx2.Response(status, request=request)


def test_rate_limit_is_retryable() -> None:
    import openai

    error = openai.RateLimitError("slow down", response=_http_response(429), body=None)
    with pytest.raises(AIRateLimited) as caught:
        provider_with(error=error).complete(make_request(), spec=OPENAI_SPEC)
    assert caught.value.retryable is True


def test_an_empty_balance_is_not_treated_as_a_rate_limit() -> None:
    """Found by running the live suite against a real key with no credit.

    OpenAI reports both as HTTP 429, and the adapter called both retryable.
    Waiting fixes a rate limit; nothing fixes an empty balance except a
    payment, so every queued job retried, every retry failed identically, and
    the logs said "rate limited" while the real problem was a billing page.
    """
    import openai

    error = openai.RateLimitError(
        "You have no credits remaining.",
        response=_http_response(429),
        body={
            "error": {
                "message": "You have no credits remaining.",
                "type": "insufficient_quota",
                "code": "credit_balance_exhausted",
            }
        },
    )

    with pytest.raises(AIQuotaExhausted) as caught:
        provider_with(error=error).complete(make_request(), spec=OPENAI_SPEC)

    assert caught.value.retryable is False
    # Written for a person: this is one of the few provider failures the
    # customer can act on themselves.
    assert "credit" in str(caught.value).lower()


def test_a_genuine_rate_limit_is_still_retryable() -> None:
    """The quota check must not swallow the case it sits in front of."""
    import openai

    error = openai.RateLimitError(
        "Rate limit reached for gpt-5-nano",
        response=_http_response(429),
        body={"error": {"message": "Rate limit reached", "type": "rate_limit_error"}},
    )

    with pytest.raises(AIRateLimited) as caught:
        provider_with(error=error).complete(make_request(), spec=OPENAI_SPEC)

    assert caught.value.retryable is True


@pytest.mark.django_db
def test_a_quota_failure_is_recorded_once_and_not_retried(organization: Any) -> None:
    """The runner must not pay for a second attempt it knows will fail."""
    import openai

    from apps.ai.models import AIJob, AIJobStatus
    from apps.ai.runner import run_prompt

    error = openai.RateLimitError(
        "You have no credits remaining.",
        response=_http_response(429),
        body={"error": {"type": "insufficient_quota"}},
    )
    provider = provider_with(error=error)

    with pytest.raises(AIQuotaExhausted):
        run_prompt(
            organization=organization,
            prompt="reply_classification",
            user_content="Take me off your list.",
            provider=provider,
        )

    job = AIJob.all_objects.get()
    assert job.status == AIJobStatus.FAILED
    assert job.attempts == 1
    assert len(provider.client.responses.calls) == 1


def test_client_error_is_not_retryable() -> None:
    """A 400 is our bug; retrying fails identically and costs twice."""
    import openai

    error = openai.BadRequestError("bad schema", response=_http_response(400), body=None)
    with pytest.raises(AIProviderError) as caught:
        provider_with(error=error).complete(make_request(), spec=OPENAI_SPEC)
    assert caught.value.retryable is False


def test_missing_output_is_reported_rather_than_returned_as_none() -> None:
    response = SimpleNamespace(
        output_parsed=None,
        output_text="",
        status="completed",
        error=None,
        incomplete_details=None,
        output=[],
        usage=fake_usage(input_tokens=10, output_tokens=1),
    )
    with pytest.raises(AIOutputInvalid):
        provider_with(response).complete(make_request(), spec=OPENAI_SPEC)


# --------------------------------------------------------------------------- #
# Runner integration
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_runner_works_end_to_end_on_openai(organization: Any) -> None:
    """The runner is vendor-agnostic: same call, same job record."""
    from apps.ai.models import AIJobStatus
    from apps.ai.prompts import Prompt
    from apps.ai.runner import run_prompt

    response = SimpleNamespace(
        output_parsed=Answer(answer="done"),
        output_text="",
        status="completed",
        error=None,
        incomplete_details=None,
        output=[],
        usage=fake_usage(input_tokens=5_000, output_tokens=200, cached=4_000),
    )

    prompt = Prompt(
        name="_test_openai",
        version=1,
        tier=Tier.STANDARD,
        output_schema=Answer,
        instructions="Answer.",
    )

    result = run_prompt(
        organization=organization,
        prompt=prompt,
        user_content="hello",
        provider=provider_with(response),
    )

    assert result.output.answer == "done"
    assert result.job.status == AIJobStatus.SUCCEEDED
    assert result.job.provider == "openai"
    assert result.job.cache_read_tokens == 4_000
    assert result.job.input_tokens == 1_000
    assert result.job.cost_micro_usd > 0
