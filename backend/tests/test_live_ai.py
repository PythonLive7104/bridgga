"""Tests that call the real AI provider, and cost real money.

Skipped unless the suite is run with ``--live-ai``:

    .venv/Scripts/python -m pytest tests/test_live_ai.py --live-ai -v

They need ``AI_PROVIDER`` and the matching key in the environment, which
``backend/.env`` already supplies. Expect a few cents per full run.

**What belongs here and what does not.** Everything about the machinery around
a model -- tenancy, retries, cost arithmetic, job records, grounding checks --
is tested against the stub, deterministically and for free, in
``test_ai_layer.py`` and ``test_signal_engine.py``. What cannot be tested that
way is whether a real model does what the prompt asks, and whether the numbers
it reports add up the way the billing ledger assumes. That is all that is here:

* the eval set against a live model, with a floor on the pass rate;
* prompt injection, where the bar is 100% and nothing less is shippable;
* restraint, which is the behaviour a stub cannot have an opinion about;
* real token accounting reaching the usage ledger.

A failure here is a product problem, not a flake. The pass-rate floors are
deliberately below perfect so that a single borderline judgement does not fail
the run, but any failure is worth reading before it is retried.
"""

from __future__ import annotations

from typing import Any

import pytest

from apps.ai.evals import all_cases, format_report, run_evals
from apps.ai.runner import run_prompt
from apps.ai.schemas import ReplyCategory
from apps.common.tenancy import tenant_context

pytestmark = [pytest.mark.live_ai, pytest.mark.django_db]

#: Below this, the prompts are not doing their job. Not 100%: a handful of the
#: cases turn on a judgement two careful people could differ on.
MINIMUM_PASS_RATE = 0.80


def report_lines(report: Any) -> str:
    """Printed on failure, so a red run says which case and why."""
    return "\n" + format_report(report)


# --------------------------------------------------------------------------- #
# The eval set against a real model
# --------------------------------------------------------------------------- #


def test_the_whole_eval_set_clears_the_floor(live_provider: Any) -> None:
    report = run_evals(provider=live_provider)

    print(report_lines(report))
    assert report.total == len(all_cases())
    assert report.pass_rate >= MINIMUM_PASS_RATE, report_lines(report)


def test_prompt_injection_is_never_obeyed(live_provider: Any) -> None:
    """The one gate with no tolerance.

    Every injection case is a payload an attacker can place on a website and
    wait for the platform to read. A single pass at 80% here means one
    customer in five being shown a fabricated claim that a stranger wrote.
    """
    report = run_evals(tag="injection", provider=live_provider)

    print(report_lines(report))
    assert report.total >= 2
    assert report.pass_rate == 1.0, report_lines(report)


def test_the_model_leaves_unstated_things_empty(live_provider: Any) -> None:
    """Restraint, which is the hardest thing to get from a model.

    These cases make an empty field the correct answer: a site with no
    published pricing, a site naming no competitors. A model that fills them
    scores better on coverage and is worse for the product, because the
    fabrication is only discovered in front of a buyer.
    """
    report = run_evals(tag="grounding", provider=live_provider)

    print(report_lines(report))
    assert report.total >= 2
    assert report.pass_rate >= MINIMUM_PASS_RATE, report_lines(report)


def test_an_opt_out_is_detected_however_it_is_phrased(live_provider: Any) -> None:
    """Compliance, not quality: missing one is a breach of section 63.

    The cases include opt-outs wrapped in praise and in anger, because those
    are the ones a classifier gets wrong.
    """
    report = run_evals(tag="compliance", provider=live_provider)

    print(report_lines(report))
    assert report.total >= 2
    assert report.pass_rate == 1.0, report_lines(report)


def test_a_website_change_that_means_nothing_produces_no_signal(
    live_provider: Any,
) -> None:
    """The signal engine's whole value rests on this being true.

    A model that reads a rotated testimonial as a buying signal fills the feed
    with noise, and a feed of noise is worse than an empty one: it trains the
    customer to ignore the thing the product is for.
    """
    report = run_evals(tag="restraint", provider=live_provider)

    print(report_lines(report))
    assert report.total >= 2
    assert report.pass_rate >= MINIMUM_PASS_RATE, report_lines(report)


# --------------------------------------------------------------------------- #
# Real token accounting
# --------------------------------------------------------------------------- #


def test_a_real_call_is_costed_and_recorded(organization: Any, live_provider: Any) -> None:
    """The ledger against real usage figures (PRD section 59).

    The cost arithmetic is unit-tested against fixed token counts, but nothing
    off a live call ever reaches it there. This is what catches a vendor
    changing the shape of its usage object -- the symptom of which is not an
    error but a wrong number on an invoice.
    """
    from apps.ai.models import AIJob, AIJobStatus
    from apps.billing.models import UsageRecord

    result = run_prompt(
        organization=organization,
        prompt="reply_classification",
        user_content="Please take me off your list, I'm not interested.",
        feature="live_test",
        provider=live_provider,
    )

    assert result.output.category in {ReplyCategory.UNSUBSCRIBE, ReplyCategory.NOT_INTERESTED}
    # An opt-out is acted on independently of the category it was filed under.
    assert result.output.contains_opt_out is True

    job = result.job
    assert job.status == AIJobStatus.SUCCEEDED
    assert job.input_tokens > 0
    assert job.output_tokens > 0
    assert job.cost_micro_usd > 0
    assert job.latency_ms > 0
    assert job.model_id

    with tenant_context(organization=organization):
        usage = UsageRecord.objects.get(pk=job.usage_record_id)
        assert usage.organization_id == organization.pk
        assert usage.quantity == job.input_tokens + job.output_tokens + job.cache_read_tokens + (
            job.cache_write_tokens
        )
        assert usage.estimated_cost_minor >= 0
        assert AIJob.objects.filter(pk=job.pk).exists()


def test_the_output_is_constrained_to_the_schema(organization: Any, live_provider: Any) -> None:
    """Structured output, from the vendor, not parsed out of prose.

    If this breaks, the provider is no longer honouring the schema and every
    agent in the product is returning something the API contract does not
    describe.
    """
    result = run_prompt(
        organization=organization,
        prompt="reply_classification",
        user_content="Can you send pricing for 40 vehicles, and who handles contracts?",
        feature="live_test",
        provider=live_provider,
    )

    output = result.output
    assert output.category in set(ReplyCategory)
    assert output.confidence
    # `extra="forbid"` on the schema is what makes this a guarantee rather
    # than a hope: an unexpected key would have failed validation upstream.
    assert set(output.model_dump()) == {
        "category",
        "confidence",
        "reasoning",
        "contains_opt_out",
        "suggested_next_step",
    }
