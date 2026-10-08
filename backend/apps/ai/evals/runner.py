"""Eval runner.

Runs cases through the real prompt against a provider and scores the output.
Deliberately does not touch the database: an eval is a measurement of prompt
quality, not a product operation, and keeping it stateless means it can run in
CI, from a shell, or against a scratch model without a tenant.

Cost is reported on every run. An eval set that nobody knows the price of stops
being run.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import structlog

from apps.ai.evals.cases import CheckResult, EvalCase, all_cases
from apps.ai.pricing import resolve_model
from apps.ai.prompts import get_prompt
from apps.ai.providers.base import AIProvider, AIProviderError
from apps.ai.registry import get_provider
from apps.ai.runner import build_completion_request

logger = structlog.get_logger(__name__)


@dataclass(slots=True)
class CaseOutcome:
    case: EvalCase
    passed: bool
    checks: list[tuple[str, CheckResult]] = field(default_factory=list)
    error: str = ""
    cost_micro_usd: int = 0
    latency_ms: float = 0.0

    @property
    def failures(self) -> list[tuple[str, CheckResult]]:
        return [(name, result) for name, result in self.checks if not result.passed]


@dataclass(slots=True)
class EvalReport:
    outcomes: list[CaseOutcome] = field(default_factory=list)
    model_id: str = ""
    provider: str = ""

    @property
    def total(self) -> int:
        return len(self.outcomes)

    @property
    def passed(self) -> int:
        return sum(1 for outcome in self.outcomes if outcome.passed)

    @property
    def pass_rate(self) -> float:
        return (self.passed / self.total) if self.total else 0.0

    @property
    def cost_micro_usd(self) -> int:
        return sum(outcome.cost_micro_usd for outcome in self.outcomes)

    def by_tag(self) -> dict[str, tuple[int, int]]:
        """Pass counts per tag.

        Per-tag reporting matters more than the headline here: a set that is
        95% overall but failing every `injection` case is not safe to ship,
        and an aggregate number hides exactly that.
        """
        counts: dict[str, tuple[int, int]] = {}
        for outcome in self.outcomes:
            for tag in outcome.case.tags:
                passed, total = counts.get(tag, (0, 0))
                counts[tag] = (passed + (1 if outcome.passed else 0), total + 1)
        return counts

    def failures(self) -> list[CaseOutcome]:
        return [outcome for outcome in self.outcomes if not outcome.passed]


def run_case(case: EvalCase, *, provider: AIProvider | None = None) -> CaseOutcome:
    prompt = get_prompt(case.prompt_name)
    provider = provider or get_provider()
    spec = resolve_model(prompt.tier)

    # The same builder production uses, so the eval exercises the real prompt
    # text and the real untrusted-content fencing.
    request = build_completion_request(
        prompt=prompt,
        user_content=case.user_content,
        cacheable_context=case.cacheable_context,
    )

    try:
        response = provider.complete(request, spec=spec)
    except AIProviderError as exc:
        return CaseOutcome(case=case, passed=False, error=f"{type(exc).__name__}: {exc}")

    checks: list[tuple[str, CheckResult]] = []
    for expectation in case.expectations:
        try:
            result = expectation.check(response.parsed, case)
        except Exception as exc:  # a broken check must not halt the run
            result = CheckResult.fail(f"check raised {type(exc).__name__}: {exc}")
        checks.append((getattr(expectation, "name", type(expectation).__name__), result))

    return CaseOutcome(
        case=case,
        passed=all(result.passed for _, result in checks),
        checks=checks,
        cost_micro_usd=response.usage.cost_micro_usd(spec),
        latency_ms=response.latency_ms,
    )


def run_evals(
    *,
    prompt_name: str = "",
    tag: str = "",
    provider: AIProvider | None = None,
) -> EvalReport:
    provider = provider or get_provider()
    cases = all_cases(prompt_name=prompt_name, tag=tag)

    report = EvalReport(provider=provider.name)
    for case in cases:
        outcome = run_case(case, provider=provider)
        report.outcomes.append(outcome)
        if not report.model_id:
            report.model_id = resolve_model(get_prompt(case.prompt_name).tier).model_id

    logger.info(
        "evals_complete",
        provider=report.provider,
        total=report.total,
        passed=report.passed,
        cost_micro_usd=report.cost_micro_usd,
    )
    return report


def format_report(report: EvalReport) -> str:
    """Human-readable summary for a terminal or a CI log."""
    lines: list[str] = []
    lines.append(f"Provider: {report.provider}")
    lines.append(f"Cases:    {report.passed}/{report.total} passed ({report.pass_rate:.0%})")
    lines.append(f"Cost:     ${report.cost_micro_usd / 1_000_000:.4f}")

    tags = report.by_tag()
    if tags:
        lines.append("")
        lines.append("By tag:")
        for tag in sorted(tags):
            passed, total = tags[tag]
            flag = "" if passed == total else "   <-- failing"
            lines.append(f"  {tag:<16} {passed}/{total}{flag}")

    failures = report.failures()
    if failures:
        lines.append("")
        lines.append("Failures:")
        for outcome in failures:
            lines.append(f"  {outcome.case.id}")
            if outcome.error:
                lines.append(f"      error: {outcome.error}")
            for name, result in outcome.failures:
                lines.append(f"      {name}: {result.detail}")
            if outcome.case.notes:
                lines.append(f"      note: {outcome.case.notes}")

    return "\n".join(lines)
