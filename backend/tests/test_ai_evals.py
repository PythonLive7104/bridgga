"""The eval harness (PRD section 106).

These test the *harness*, not model quality. A grader that silently passes
everything is worse than no eval set at all: it produces a green number that
nobody questions. So each grader is tested against an output it must reject.

Model quality is what `manage.py run_evals` measures against a real provider.
"""

from __future__ import annotations

from typing import Any

import pytest

from apps.ai.evals import all_cases, format_report, run_case, run_evals
from apps.ai.evals.cases import (
    EvalCase,
    EvidenceGrounded,
    FieldContains,
    FieldEmpty,
    FieldEquals,
    FieldNotEmpty,
    Grounded,
    MaxItems,
    read_path,
    register_case,
)
from apps.ai.providers.stub import StubProvider
from apps.ai.schemas import CompanyProfile, Confidence, Evidence, ICPDraft

SOURCE = "Acme Haulage runs trucks in Lagos. Products: Fleet Live, Fuel Guard."


def case(**overrides: Any) -> EvalCase:
    defaults: dict[str, Any] = {
        "id": "t",
        "prompt_name": "company_profile",
        "user_content": SOURCE,
    }
    defaults.update(overrides)
    return EvalCase(**defaults)


# --------------------------------------------------------------------------- #
# Graders
# --------------------------------------------------------------------------- #


def test_grounded_accepts_claims_present_in_the_source() -> None:
    profile = CompanyProfile(products=["Fleet Live", "Fuel Guard"])
    assert Grounded("products").check(profile, case()).passed


def test_grounded_rejects_an_invented_claim() -> None:
    """The failure that matters most: a plausible product the site never names."""
    profile = CompanyProfile(products=["Fleet Live", "Route Optimiser Pro"])
    result = Grounded("products").check(profile, case())
    assert not result.passed
    assert "Route Optimiser Pro" in result.detail


def test_grounded_tolerates_a_partial_name_match() -> None:
    """'Acme Haulage Limited' is grounded when the page says 'Acme Haulage'."""
    profile = CompanyProfile(company_name="Acme Haulage Limited")
    assert Grounded("company_name").check(profile, case()).passed


def test_grounded_passes_when_nothing_was_claimed() -> None:
    """Restraint is not a grounding failure."""
    assert Grounded("products").check(CompanyProfile(), case()).passed


def test_field_empty_catches_a_fabricated_value() -> None:
    profile = CompanyProfile(pricing_summary="$99/month")
    result = FieldEmpty("pricing_summary").check(profile, case())
    assert not result.passed
    assert "fabricated" in result.detail


def test_field_empty_passes_on_a_blank_field() -> None:
    assert FieldEmpty("pricing_summary").check(CompanyProfile(), case()).passed


def test_field_not_empty_catches_an_omission() -> None:
    assert not FieldNotEmpty("products").check(CompanyProfile(), case()).passed


def test_field_equals_compares_exactly() -> None:
    profile = CompanyProfile(industry="logistics")
    assert FieldEquals("industry", "logistics").check(profile, case()).passed
    assert not FieldEquals("industry", "fintech").check(profile, case()).passed


def test_field_contains_is_case_insensitive_and_searches_lists() -> None:
    profile = CompanyProfile(industry="Logistics", competitors=["QuickBooks"])
    assert FieldContains("industry", "logistics").check(profile, case()).passed
    assert FieldContains("competitors", "quickbooks").check(profile, case()).passed


def test_evidence_grounded_rejects_an_invented_quote() -> None:
    profile = CompanyProfile(
        evidence=[
            Evidence(
                claim="They are expanding",
                source_type="website",
                quote="We are opening twelve new depots next quarter",
            )
        ]
    )
    result = EvidenceGrounded().check(profile, case())
    assert not result.passed
    assert "quote not in source" in result.detail


def test_evidence_grounded_accepts_a_real_quote() -> None:
    profile = CompanyProfile(
        evidence=[
            Evidence(claim="Operates in Lagos", source_type="website", quote="runs trucks in Lagos")
        ]
    )
    assert EvidenceGrounded().check(profile, case()).passed


def test_max_items_bounds_a_list() -> None:
    profile = CompanyProfile(products=["a", "b", "c"])
    assert MaxItems("products", 3).check(profile, case()).passed
    assert not MaxItems("products", 2).check(profile, case()).passed


def test_read_path_walks_nested_models() -> None:
    icp = ICPDraft(buyer={"job_titles": ["Fleet Manager"]})
    assert read_path(icp, "buyer.job_titles") == ["Fleet Manager"]
    assert read_path(icp, "buyer.nonexistent") is None


def test_graders_cover_both_outcomes() -> None:
    """A grader that cannot fail is decoration, not a check."""
    profile_good = CompanyProfile(products=["Fleet Live"])
    profile_bad = CompanyProfile(products=["Invented Thing"])

    grader = Grounded("products")
    assert grader.check(profile_good, case()).passed
    assert not grader.check(profile_bad, case()).passed


# --------------------------------------------------------------------------- #
# Dataset
# --------------------------------------------------------------------------- #


def test_dataset_is_populated() -> None:
    """Guards the guard: an empty set would make every run vacuously green."""
    cases = all_cases()
    assert len(cases) >= 10


def test_every_case_has_at_least_one_expectation() -> None:
    for item in all_cases():
        assert item.expectations, f"{item.id} asserts nothing"


def test_every_case_targets_a_registered_prompt() -> None:
    from apps.ai.prompts import all_prompts

    known = set(all_prompts())
    for item in all_cases():
        assert item.prompt_name in known, f"{item.id} targets unknown prompt"


def test_case_ids_are_unique() -> None:
    ids = [item.id for item in all_cases()]
    assert len(ids) == len(set(ids))


def test_duplicate_case_id_is_refused() -> None:
    existing = all_cases()[0]
    with pytest.raises(ValueError, match="Duplicate eval case id"):
        register_case(EvalCase(id=existing.id, prompt_name="company_profile", user_content="x"))


#: Phrasings that actually attempt an instruction override. Matched case
#: insensitively, because an injection payload shouting in capitals is still
#: an injection payload -- the first version of this test demanded one exact
#: capitalisation and failed on a case that was a perfectly good attack.
_OVERRIDE_PHRASINGS = (
    "system override",
    "ignore all previous",
    "ignore previous",
    "ignore the above",
    "disregard",
    "you are now",
    "new instructions",
)


def test_security_cases_exist_for_prompt_injection() -> None:
    """The guardrail in GUARDRAILS needs a case that would catch its removal."""
    injection = all_cases(tag="injection")
    assert injection, "no prompt-injection eval case"
    for item in injection:
        content = item.user_content.lower() + item.cacheable_context.lower()
        assert any(phrase in content for phrase in _OVERRIDE_PHRASINGS), (
            f"{item.id} is tagged `injection` but carries no override attempt"
        )


def test_compliance_cases_assert_opt_out_detection() -> None:
    """Missing an opt-out is a compliance breach, so it is covered explicitly."""
    compliance = all_cases(tag="compliance")
    assert compliance
    for item in compliance:
        assert any(getattr(exp, "path", "") == "contains_opt_out" for exp in item.expectations), (
            f"{item.id} does not assert contains_opt_out"
        )


def test_classification_cases_cover_the_awkward_labels() -> None:
    ids = {item.id for item in all_cases(prompt_name="reply_classification")}
    for expected in ("out_of_office", "referral", "wrong_person", "objection"):
        assert any(expected in case_id for case_id in ids), f"no case for {expected}"


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #


def test_run_case_scores_a_passing_output() -> None:
    target = case(expectations=[FieldEmpty("pricing_summary"), Grounded("products")])
    provider = StubProvider(responses=[CompanyProfile(products=["Fleet Live"])])

    outcome = run_case(target, provider=provider)

    assert outcome.passed
    assert len(outcome.checks) == 2
    assert outcome.cost_micro_usd > 0


def test_run_case_reports_which_check_failed() -> None:
    target = case(expectations=[FieldEmpty("pricing_summary"), Grounded("products")])
    provider = StubProvider(
        responses=[CompanyProfile(pricing_summary="$99/mo", products=["Invented"])]
    )

    outcome = run_case(target, provider=provider)

    assert not outcome.passed
    failed = {name for name, _ in outcome.failures}
    assert failed == {"field_empty", "grounded"}


def test_provider_error_fails_the_case_rather_than_the_run() -> None:
    from apps.ai.providers.base import AIProviderError

    target = case(expectations=[FieldEmpty("pricing_summary")])
    provider = StubProvider(responses=[AIProviderError("boom")])

    outcome = run_case(target, provider=provider)

    assert not outcome.passed
    assert "boom" in outcome.error


def test_a_broken_grader_does_not_halt_the_run() -> None:
    """One bad check should not cost a whole (paid) eval run."""

    class Exploding:
        name = "exploding"

        def check(self, output: Any, case: Any) -> Any:
            raise RuntimeError("grader bug")

    target = case(expectations=[Exploding(), FieldEmpty("pricing_summary")])
    outcome = run_case(target, provider=StubProvider(responses=[CompanyProfile()]))

    assert not outcome.passed
    assert len(outcome.checks) == 2
    assert "grader bug" in outcome.failures[0][1].detail


def test_eval_run_is_tagged_and_costed() -> None:
    report = run_evals(prompt_name="reply_classification", provider=StubProvider())

    assert report.total > 0
    assert report.cost_micro_usd > 0
    assert "classification" in report.by_tag()


def test_report_surfaces_failing_tags() -> None:
    """A headline pass rate hides a category that is entirely broken."""
    report = run_evals(prompt_name="company_profile", provider=StubProvider())
    rendered = format_report(report)

    assert "Provider:" in rendered
    assert "By tag:" in rendered
    if report.failures():
        assert "Failures:" in rendered


def test_run_evals_can_filter_by_tag() -> None:
    report = run_evals(tag="injection", provider=StubProvider())
    assert report.total == len(all_cases(tag="injection"))


def test_stub_does_not_pass_quality_cases() -> None:
    """The stub returns empty placeholders, so it must not look like a good model.

    If this ever passes, the dataset has stopped asserting anything about
    content and has become a schema check wearing an eval's clothes.
    """
    report = run_evals(prompt_name="company_profile", provider=StubProvider())
    assert report.pass_rate < 1.0


def test_confidence_enum_round_trips_through_a_grader() -> None:
    profile = CompanyProfile(confidence=Confidence.LOW)
    assert FieldEquals("confidence", Confidence.LOW).check(profile, case()).passed
