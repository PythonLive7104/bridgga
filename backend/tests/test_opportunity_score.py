"""The opportunity score (PRD sections 32 and 119).

The arithmetic is the easy part. What these tests are mostly about is the
distinction the whole module is built on: **a component nobody could measure
is not a component that scored zero.**

Get that wrong and the number is confidently false in two directions at once.
Engagement data does not exist until campaigns ship, so every prospect in the
product would be capped at 90 for a whole phase. A company nobody has crawled
has no signals, so scoring its intent at 0/20 asserts "we looked and there is
nothing" when the truth is "we have not looked". Both are the kind of wrong
that nobody notices, because the output is a plausible-looking number.

So the scorers return ``None`` for "cannot assess", the weight is
redistributed across what *can* be assessed, and ``confidence`` reports how
much of the weighting was actually covered. Most of what follows is about
those three sentences holding.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from django.utils import timezone

from apps.ai.schemas import SignalType
from apps.common.models import ContactStatus
from apps.common.tenancy import tenant_context
from apps.companies import services as company_services
from apps.companies.models import LeadSignal
from apps.contacts import services as contact_services
from apps.intelligence.models import ICP
from apps.leads import services as lead_services
from apps.leads.scoring import (
    STALE_CONFIDENCE_FACTOR,
    build_context,
    score_lead,
    score_organization_leads,
    score_prospect,
)
from apps.leads.scoring_models import (
    DEFAULT_WEIGHTS,
    MAX_WEIGHT,
    ScoreComponent,
    ScoringProfile,
    band_for,
    default_weights,
    merge_weights,
    weights_for,
)
from apps.organizations.roles import Role

pytestmark = pytest.mark.django_db

PROSPECTS_URL = "/api/v1/prospects"
SCORING_URL = "/api/v1/scoring/profile"


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture
def company(organization: Any) -> Any:
    made, _ = company_services.upsert_company(
        organization=organization,
        name="Harmattan Fleet",
        website="https://harmattanfleet.example",
        industry="Logistics software",
        country="NG",
        employee_range="51-200",
        business_model="B2B SaaS subscription",
        source="test",
    )
    return made


@pytest.fixture
def icp(organization: Any) -> ICP:
    with tenant_context(organization=organization):
        return ICP.objects.create(
            organization=organization,
            name="West African haulage operators",
            industries=["Logistics"],
            countries=["NG", "GH"],
            employee_range="25-250",
            business_models=["B2B SaaS subscription"],
            technologies=["Shopify", "HubSpot"],
            pain_signals=[
                {"type": "hiring", "description": "hiring fleet or logistics managers"},
                {"type": "funding", "description": "raised recently"},
            ],
            is_active=True,
        )


def make_signal(organization: Any, company: Any, **fields: Any) -> LeadSignal:
    defaults = {
        "signal_type": SignalType.HIRING,
        "title": "Hiring three fleet supervisors",
        "fingerprint": fields.get("signal_type", "hiring"),
        "strength": 80,
        "detector": "hiring_page",
        "evidence": [
            {
                "claim": "Careers page lists the role",
                "source_type": "careers_page",
                "source_url": "https://harmattanfleet.example/careers",
                "quote": "Senior Fleet Manager",
            }
        ],
    }
    with tenant_context(organization=organization):
        return LeadSignal.objects.create(
            organization=organization, company=company, **(defaults | fields)
        )


def make_lead(organization: Any, company: Any, icp: Any = None) -> Any:
    source = lead_services.get_or_create_source(
        organization=organization, name="Test", kind="manual"
    )
    lead, _ = lead_services.create_lead(
        organization=organization, company=company, source=source, icp=icp
    )
    return lead


def select_market(organization: Any, icp: Any, code: str = "NG") -> Any:
    """Mark a country as chosen by the customer, as the markets screen does."""
    from apps.intelligence.models import CountryProfile, MarketRecommendation

    country, _ = CountryProfile.objects.get_or_create(
        code=code, defaults={"name": "Nigeria", "currency": "NGN", "is_launch_market": True}
    )
    with tenant_context(organization=organization):
        return MarketRecommendation.objects.create(
            organization=organization,
            country=country,
            icp=icp,
            fit="high",
            score=90,
            reasoning="Largest haulage market in the region.",
            is_selected=True,
        )


def component(result: Any, name: str) -> Any:
    return next(item for item in result.components if item.component == name)


# --------------------------------------------------------------------------- #
# The configured weighting (section 32)
# --------------------------------------------------------------------------- #


def test_the_default_weighting_is_the_one_the_prd_specifies() -> None:
    """Section 32's table, pinned.

    Not a tautology: these are product decisions written down in the PRD, and
    a casual edit here silently rescores every organization that has not
    overridden them.
    """
    assert DEFAULT_WEIGHTS == {
        "icp_fit": 25,
        "buying_intent": 20,
        "pain_evidence": 15,
        "company_growth": 10,
        "technology_fit": 10,
        "geographic_fit": 5,
        "contact_quality": 5,
        "engagement": 10,
    }
    assert sum(DEFAULT_WEIGHTS.values()) == 100
    assert set(DEFAULT_WEIGHTS) == set(ScoreComponent.values)


def test_the_bands_match_the_ones_the_interface_colours() -> None:
    """The server names the band; the client colours the badge.

    ``scoreBand`` in web/src/lib/utils.ts uses 75 and 45. A prospect labelled
    "high opportunity" in amber is a bug nobody can explain to a customer.
    """
    assert band_for(100) == "high"
    assert band_for(75) == "high"
    assert band_for(74) == "medium"
    assert band_for(45) == "medium"
    assert band_for(44) == "low"
    assert band_for(0) == "low"


def test_weights_are_cleaned_rather_than_rejected() -> None:
    """These arrive from a form, where every mistake here is an easy one."""
    # Unknown components are dropped; missing ones keep their default, so a
    # component added in a later release does not start life at zero.
    assert merge_weights({"icp_fit": 40, "nonsense": 90})["icp_fit"] == 40
    assert "nonsense" not in merge_weights({"nonsense": 90})
    assert merge_weights({})["engagement"] == DEFAULT_WEIGHTS["engagement"]

    # Out of range is clamped, not refused.
    assert merge_weights({"icp_fit": -5})["icp_fit"] == 0
    assert merge_weights({"icp_fit": 500})["icp_fit"] == MAX_WEIGHT

    # Everything zero would make the score undefined, not zero.
    assert merge_weights(dict.fromkeys(ScoreComponent.values, 0)) == DEFAULT_WEIGHTS
    assert merge_weights("not a mapping") == DEFAULT_WEIGHTS


def test_an_organization_without_a_profile_uses_the_prd_defaults(organization: Any) -> None:
    assert weights_for(organization) == DEFAULT_WEIGHTS


def test_weights_need_not_add_up_to_a_hundred(organization: Any, company: Any, icp: ICP) -> None:
    """ "Weigh these equally" is a sensible thing to mean.

    The engine divides by the total, so a customer who types 10 into every
    box gets equal weighting rather than a score out of 80.
    """
    make_signal(organization, company)

    equal_tens = score_prospect(company, weights=dict.fromkeys(ScoreComponent.values, 10))
    equal_hundreds = score_prospect(company, weights=dict.fromkeys(ScoreComponent.values, 100))

    assert equal_tens.score == equal_hundreds.score


# --------------------------------------------------------------------------- #
# Unmeasured is not zero -- the core of the module
# --------------------------------------------------------------------------- #


def test_a_company_nobody_has_examined_has_no_intent_score(
    organization: Any, company: Any, icp: ICP
) -> None:
    """ "We have not looked" and "there is nothing" are different claims.

    Scoring an unexamined company's intent at 0/20 is the second one, and it
    is the kind of wrong that a plausible number hides.
    """
    result = score_prospect(company)

    intent = component(result, ScoreComponent.BUYING_INTENT)
    assert intent.available is False
    assert "not been examined" in intent.reason
    # And the weight it would have carried is not counted against the score.
    assert ScoreComponent.BUYING_INTENT not in {c.component for c in result.assessed}


def test_a_company_that_was_examined_and_had_nothing_scores_zero(
    organization: Any, company: Any, icp: ICP
) -> None:
    """The other half of the same distinction: a real, assessed zero."""
    from apps.intelligence.models import SnapshotStatus, WebsiteSnapshot

    with tenant_context(organization=organization):
        WebsiteSnapshot.objects.create(
            organization=organization,
            company=company,
            requested_url="https://harmattanfleet.example/",
            status=SnapshotStatus.OK,
        )

    intent = component(score_prospect(company), ScoreComponent.BUYING_INTENT)

    assert intent.available is True
    assert intent.value == 0.0


def test_engagement_is_never_assessed_yet_and_a_prospect_can_still_reach_100(
    organization: Any, company: Any, icp: ICP
) -> None:
    """The test that justifies the whole design.

    Engagement is 10% of section 32's weighting and no engagement data exists
    until Phase 3. Treating it as zero would cap every prospect in the
    product at 90 for an entire phase -- a ceiling nobody would think to look
    for, in a number everybody would quote.
    """
    # Everything assessable, and all of it perfect.
    make_signal(organization, company, signal_type=SignalType.FUNDING, strength=100)
    make_signal(organization, company, signal_type=SignalType.HIRING, strength=100)
    company_services.record_technology(company=company, name="Shopify", source="test")
    company_services.record_technology(company=company, name="HubSpot", source="test")
    contact_services.upsert_person(
        organization=organization,
        company=company,
        email="ada@harmattanfleet.example",
        source="test",
        job_title="Head of Operations",
        email_status=ContactStatus.VERIFIED,
        is_decision_maker=True,
        phone="+2348000000000",
    )
    select_market(organization, icp)

    result = score_prospect(company)

    assert component(result, ScoreComponent.ENGAGEMENT).available is False
    assert result.score == 100
    assert result.band == "high"
    # Confidence says what the score does not: 90 of the 100 configured
    # weight was assessable, so this is a complete answer to an incomplete
    # question.
    assert result.confidence == 90


def test_confidence_is_the_share_of_the_weighting_that_was_assessed(
    organization: Any, company: Any
) -> None:
    """With no ICP and no crawl, almost nothing can be judged."""
    result = score_prospect(company)

    assessed_weight = sum(c.weight for c in result.assessed)
    total_weight = sum(c.weight for c in result.components)

    assert result.confidence == round(100 * assessed_weight / total_weight)
    assert result.confidence < 50, "an unexamined company with no ICP cannot be judged confidently"


def test_a_stale_company_record_lowers_confidence_not_the_score(
    organization: Any, company: Any, icp: ICP
) -> None:
    """Age is a statement about certainty, not about fit.

    Discounting the score itself would mean an old record about a perfect-fit
    company ranking below a fresh record about a poor one.
    """
    make_signal(organization, company, signal_type=SignalType.FUNDING, strength=100)

    fresh = score_prospect(company)

    with tenant_context(organization=organization):
        company.last_verified_at = timezone.now() - timezone.timedelta(days=400)
        company.collected_at = company.last_verified_at
        company.save(update_fields=["last_verified_at", "collected_at"])
    company.refresh_from_db()

    stale = score_prospect(company)

    assert stale.score == fresh.score
    assert stale.confidence == round(fresh.confidence * STALE_CONFIDENCE_FACTOR)
    assert stale.assumptions["company_record_is_stale"] is True


def test_dropped_weight_is_redistributed_across_what_remains(
    organization: Any, company: Any, icp: ICP
) -> None:
    """A component's effective weight is what it actually counted for.

    The gap between configured and effective weight is the explanation people
    most often want for a score and are least often given.
    """
    result = score_prospect(company)
    icp_fit = component(result, ScoreComponent.ICP_FIT)

    effective = result.effective_weight(icp_fit)

    assert icp_fit.weight == 25
    assert effective > 25, "ICP fit should carry more when other components cannot be assessed"
    assert sum(result.effective_weight(c) for c in result.assessed) == pytest.approx(100.0)
    assert result.effective_weight(component(result, ScoreComponent.ENGAGEMENT)) == 0.0


def test_a_broken_component_is_recorded_as_unassessed(
    organization: Any, company: Any, icp: ICP, monkeypatch: Any
) -> None:
    """One bad scorer must not cost the whole score, or silently change it.

    Dropping it from the list would quietly reweight everything else without
    saying so, so it is reported as unassessed with the reason visible.
    """
    from apps.leads import scoring

    def exploding(context: Any, weight: int) -> Any:
        raise RuntimeError("bad arithmetic")

    monkeypatch.setitem(scoring.SCORERS, ScoreComponent.GEOGRAPHIC_FIT, exploding)

    result = score_prospect(company)
    broken = component(result, ScoreComponent.GEOGRAPHIC_FIT)

    assert broken.available is False
    assert "could not be calculated" in broken.reason
    assert len(result.components) == len(ScoreComponent.values)


# --------------------------------------------------------------------------- #
# ICP fit
# --------------------------------------------------------------------------- #


def test_icp_fit_counts_only_the_criteria_the_icp_states(
    organization: Any, company: Any, icp: ICP
) -> None:
    """An ICP that specifies two things is not failed for the other six."""
    with tenant_context(organization=organization):
        icp.business_models = []
        icp.employee_range = ""
        icp.save(update_fields=["business_models", "employee_range"])

    fit = component(score_prospect(company), ScoreComponent.ICP_FIT)

    assert fit.value == 1.0
    assert sorted(fit.detail["matched"]) == ["country", "industry"]


def test_icp_fit_matches_a_headcount_range_numerically(
    organization: Any, company: Any, icp: ICP
) -> None:
    """ "25-250" and "51-200" overlap; as strings they share nothing.

    The ICP's range is free text written by a model and the company's comes
    from a fixed band, so neither a string match nor a shared vocabulary
    works.
    """
    fit = component(score_prospect(company), ScoreComponent.ICP_FIT)

    assert "size" in fit.detail["matched"]
    assert fit.value == 1.0


def test_an_unreadable_icp_range_is_skipped_rather_than_failed(
    organization: Any, company: Any, icp: ICP
) -> None:
    """A model that writes "mid-market" has not said the company is too big."""
    with tenant_context(organization=organization):
        icp.employee_range = "mid-market"
        icp.save(update_fields=["employee_range"])

    fit = component(score_prospect(company), ScoreComponent.ICP_FIT)

    assert "size" not in fit.detail["matched"]
    assert "size" not in fit.detail["missed"]
    assert fit.value == 1.0


@pytest.mark.parametrize(
    ("industry", "icp_industries", "matches"),
    [
        # The failure this was written for, found on real data: an ICP the
        # agent wrote as "Digital marketing agencies (paid media/performance)"
        # scored 0.00 against a company recorded as "Digital marketing
        # agency". An exact conceptual match, defeated by a plural and a
        # parenthetical -- and ICP fit is a quarter of the whole score.
        ("Digital marketing agency", ["Digital marketing agencies (paid media/performance)"], True),
        ("Performance marketing agency", ["Digital marketing agencies (paid media)"], True),
        ("Logistics software", ["Logistics"], True),
        ("Logistics", ["Logistics software"], True),
        # Still blunt where it should be. Sharing one generic word is not a
        # match, or every agency on earth matches every ICP that says agency.
        ("Advertising agency", ["Digital marketing agencies (paid media/performance)"], False),
        ("E-commerce retail", ["Digital marketing agencies"], False),
        ("Mining", ["Logistics"], False),
    ],
)
def test_industry_matching_survives_how_a_model_writes_english(
    organization: Any, industry: str, icp_industries: list[str], matches: bool
) -> None:
    """The ICP is written by a model in prose; the company comes from a list.

    Neither side controls the other's wording, so comparing whole strings
    means a quarter of the score turns on whether a sentence happened to be
    pluralised.
    """
    with tenant_context(organization=organization):
        ICP.objects.create(
            organization=organization,
            name="Test ICP",
            industries=icp_industries,
            is_active=True,
        )
    company, _ = company_services.upsert_company(
        organization=organization,
        name="Candidate",
        website="https://candidate.example",
        industry=industry,
        source="test",
    )

    fit = component(score_prospect(company), ScoreComponent.ICP_FIT)

    assert (fit.value == 1.0) is matches, fit.reason


def test_a_company_matching_nothing_scores_zero_on_fit(organization: Any, icp: ICP) -> None:
    other, _ = company_services.upsert_company(
        organization=organization,
        name="Kano Farms",
        website="https://kanofarms.example",
        industry="Agriculture",
        country="EG",
        employee_range="1000+",
        business_model="Direct retail",
        source="test",
    )

    fit = component(score_prospect(other), ScoreComponent.ICP_FIT)

    assert fit.value == 0.0
    assert fit.evidence == []


def test_without_an_icp_fit_cannot_be_judged(organization: Any, company: Any) -> None:
    fit = component(score_prospect(company), ScoreComponent.ICP_FIT)

    assert fit.available is False
    assert "No active ICP" in fit.reason


# --------------------------------------------------------------------------- #
# Signals: intent, growth, pain
# --------------------------------------------------------------------------- #


def test_a_live_funding_signal_is_buying_intent(organization: Any, company: Any, icp: ICP) -> None:
    make_signal(organization, company, signal_type=SignalType.FUNDING, strength=90)

    intent = component(score_prospect(company), ScoreComponent.BUYING_INTENT)

    assert intent.available is True
    assert intent.value > 0.8
    # The signal's own evidence travels with the score, so following the
    # number back to a page is one click rather than three screens.
    assert intent.evidence[0]["quote"] == "Senior Fleet Manager"
    assert intent.evidence[0]["source_url"].endswith("/careers")


def test_an_expired_signal_does_not_move_the_score(
    organization: Any, company: Any, icp: ICP
) -> None:
    """The expiry in section 33 has to mean something downstream."""
    make_signal(
        organization,
        company,
        signal_type=SignalType.FUNDING,
        strength=100,
        expires_at=timezone.now() - timezone.timedelta(days=1),
    )

    intent = component(score_prospect(company), ScoreComponent.BUYING_INTENT)

    assert intent.available is True, "we examined this company"
    assert intent.value == 0.0


def test_the_strongest_signal_dominates_rather_than_the_count(
    organization: Any, company: Any, icp: ICP
) -> None:
    """Otherwise six weak signals outrank one funding round."""
    weak, _ = company_services.upsert_company(
        organization=organization, name="Weak", website="https://weak.example", source="test"
    )
    for index in range(3):
        make_signal(
            organization,
            weak,
            signal_type=SignalType.ADVERTISING,
            strength=20,
            fingerprint=f"ad-{index}",
        )

    strong, _ = company_services.upsert_company(
        organization=organization, name="Strong", website="https://strong.example", source="test"
    )
    make_signal(organization, strong, signal_type=SignalType.FUNDING, strength=95)

    weak_value = component(score_prospect(weak), ScoreComponent.BUYING_INTENT).value
    strong_value = component(score_prospect(strong), ScoreComponent.BUYING_INTENT).value

    assert strong_value > weak_value


def test_growth_and_intent_are_different_questions(
    organization: Any, company: Any, icp: ICP
) -> None:
    """Hiring says they will need more; funding says they are shopping."""
    make_signal(organization, company, signal_type=SignalType.HIRING, strength=90)

    result = score_prospect(company)

    assert component(result, ScoreComponent.COMPANY_GROWTH).value > 0.8
    assert component(result, ScoreComponent.BUYING_INTENT).value == 0.0


def test_pain_evidence_is_the_icp_meeting_the_detectors(
    organization: Any, company: Any, icp: ICP
) -> None:
    """What the closed SignalType vocabulary exists for.

    The ICP names observable pain signals; the detectors look for exactly
    those types; this is where the two meet as a number. Without a shared
    vocabulary this component could never be more than a guess.
    """
    make_signal(organization, company, signal_type=SignalType.HIRING, strength=70)

    pain = component(score_prospect(company), ScoreComponent.PAIN_EVIDENCE)

    # The ICP watches for hiring and funding; one of the two is present.
    assert pain.value == pytest.approx(0.5)
    assert pain.detail["matched"] == ["hiring"]
    assert pain.detail["missing"] == ["funding"]
    # The ICP's own description of the pain rides along with the evidence.
    assert pain.evidence[0]["icp_pain"] == "hiring fleet or logistics managers"


def test_an_icp_with_no_pain_signals_cannot_be_judged_on_pain(
    organization: Any, company: Any, icp: ICP
) -> None:
    with tenant_context(organization=organization):
        icp.pain_signals = []
        icp.save(update_fields=["pain_signals"])

    pain = component(score_prospect(company), ScoreComponent.PAIN_EVIDENCE)

    assert pain.available is False
    assert "no observable pain signals" in pain.reason


# --------------------------------------------------------------------------- #
# Technology, geography, contact
# --------------------------------------------------------------------------- #


def test_technology_fit_is_the_overlap_with_the_icp(
    organization: Any, company: Any, icp: ICP
) -> None:
    company_services.record_technology(company=company, name="shopify", source="test")

    technology = component(score_prospect(company), ScoreComponent.TECHNOLOGY_FIT)

    # One of the two technologies the ICP names, matched case-insensitively.
    assert technology.value == pytest.approx(0.5)
    assert technology.detail["matched"] == ["Shopify"]


def test_an_unknown_technology_stack_is_not_a_bad_one(
    organization: Any, company: Any, icp: ICP
) -> None:
    """Nothing detected means nothing known, not nothing in use."""
    technology = component(score_prospect(company), ScoreComponent.TECHNOLOGY_FIT)

    assert technology.available is False
    assert "Nothing is known" in technology.reason


def test_a_selected_market_outranks_one_the_icp_merely_suggested(
    organization: Any, company: Any, icp: ICP
) -> None:
    """A selection is a decision; the ICP's country list is a recommendation."""
    icp_only = component(score_prospect(company), ScoreComponent.GEOGRAPHIC_FIT)
    assert icp_only.value == pytest.approx(0.85)

    select_market(organization, icp)
    selected = component(score_prospect(company), ScoreComponent.GEOGRAPHIC_FIT)

    assert selected.value == 1.0
    assert "selected" in selected.reason


def test_a_company_outside_every_target_market_scores_zero_on_geography(
    organization: Any, icp: ICP
) -> None:
    other, _ = company_services.upsert_company(
        organization=organization,
        name="Cairo Logistics",
        website="https://cairologistics.example",
        country="EG",
        source="test",
    )

    geography = component(score_prospect(other), ScoreComponent.GEOGRAPHIC_FIT)

    assert geography.value == 0.0
    assert geography.available is True


def test_contact_quality_prefers_a_verified_decision_maker(
    organization: Any, company: Any, icp: ICP
) -> None:
    contact_services.upsert_person(
        organization=organization,
        company=company,
        email="intern@harmattanfleet.example",
        source="test",
        email_status=ContactStatus.UNKNOWN,
    )
    contact_services.upsert_person(
        organization=organization,
        company=company,
        email="ada@harmattanfleet.example",
        source="test",
        job_title="Head of Operations",
        email_status=ContactStatus.VERIFIED,
        is_decision_maker=True,
    )

    quality = component(score_prospect(company), ScoreComponent.CONTACT_QUALITY)

    assert quality.value == 1.0
    assert "Head of Operations" in quality.reason
    assert quality.detail["contacts"] == 2


def test_contacts_that_cannot_be_written_to_score_zero_rather_than_unknown(
    organization: Any, company: Any, icp: ICP
) -> None:
    """A real negative, not a gap: we have contacts and none of them work."""
    contact_services.upsert_person(
        organization=organization,
        company=company,
        email="bounced@harmattanfleet.example",
        source="test",
        email_status=ContactStatus.BOUNCED,
    )

    quality = component(score_prospect(company), ScoreComponent.CONTACT_QUALITY)

    assert quality.available is True
    assert quality.value == 0.0
    assert "none can be contacted" in quality.reason


def test_no_contact_yet_is_not_a_bad_contact(organization: Any, company: Any, icp: ICP) -> None:
    quality = component(score_prospect(company), ScoreComponent.CONTACT_QUALITY)

    assert quality.available is False
    assert "No contact identified" in quality.reason


# --------------------------------------------------------------------------- #
# Explainability (section 119)
# --------------------------------------------------------------------------- #


def test_the_payload_carries_everything_section_119_requires(
    organization: Any, company: Any, icp: ICP
) -> None:
    make_signal(organization, company, signal_type=SignalType.FUNDING, strength=90)
    payload = score_prospect(company).payload()

    # Section 119: recommendation, reason, evidence, confidence, editable
    # assumptions.
    assert payload["recommendation"] in {
        "High opportunity",
        "Medium opportunity",
        "Low opportunity",
    }
    assert payload["reason"]
    assert payload["evidence"]
    assert isinstance(payload["confidence"], int)
    assert payload["assumptions"]["weights"] == DEFAULT_WEIGHTS

    # And the part section 32 adds: the score must be explainable per
    # component, not just in aggregate.
    assert len(payload["components"]) == len(ScoreComponent.values)
    assert {
        "component",
        "label",
        "weight",
        "effective_weight",
        "points",
        "available",
        "reason",
    } <= set(payload["components"][0])


def test_every_evidence_entry_has_the_same_shape(organization: Any, company: Any, icp: ICP) -> None:
    """Five scorers write into one list that one component iterates over.

    Found by a test that read `signal_type` off every entry and crashed on
    the one contributed by ICP fit. A key present on some entries and absent
    on others is a crash waiting for the first prospect whose best evidence
    came from a different component, so the shape is uniform and
    `signal_type` is empty rather than missing.
    """
    make_signal(organization, company, signal_type=SignalType.FUNDING, strength=90)
    company_services.record_technology(company=company, name="Shopify", source="test")
    contact_services.upsert_person(
        organization=organization,
        company=company,
        email="ada@harmattanfleet.example",
        source="test",
        email_status=ContactStatus.VERIFIED,
    )
    select_market(organization, icp)

    evidence = score_prospect(company).payload()["evidence"]
    shapes = {frozenset(entry) for entry in evidence}

    assert len(evidence) > 4, "this should span several components"
    assert len(shapes) == 1, f"evidence entries disagree on their keys: {shapes}"
    assert all("signal_type" in entry for entry in evidence)
    # And the ones that did not come from a signal say so with an empty
    # string rather than by omitting the key.
    assert any(entry["signal_type"] == "" for entry in evidence)
    assert any(entry["signal_type"] == "funding" for entry in evidence)


def test_the_payload_names_what_it_could_not_assess(
    organization: Any, company: Any, icp: ICP
) -> None:
    """A gap stated is a gap a customer can close; a gap hidden is a wrong number."""
    payload = score_prospect(company).payload()

    unassessed = {item["component"]: item["reason"] for item in payload["not_assessed"]}

    assert "engagement" in unassessed
    assert unassessed["engagement"] == "No campaign activity to measure yet."
    assert "Not assessed" in payload["reason"]


def test_the_assumptions_say_where_to_change_them(
    organization: Any, company: Any, icp: ICP
) -> None:
    """Section 119 asks for *editable* assumptions, so the payload says where."""
    assumptions = score_prospect(company).payload()["assumptions"]

    assert assumptions["icp"]["name"] == "West African haulage operators"
    assert assumptions["editable_at"]["weights"] == "/api/v1/scoring/profile"
    assert assumptions["editable_at"]["icp"].endswith("/icps")


def test_the_reason_names_the_components_that_carried_the_score(
    organization: Any, company: Any, icp: ICP
) -> None:
    make_signal(organization, company, signal_type=SignalType.FUNDING, strength=100)

    reason = score_prospect(company).reason()

    assert "icp fit" in reason.lower() or "buying intent" in reason.lower()


def test_a_prospect_with_nothing_in_its_favour_says_so(organization: Any, icp: ICP) -> None:
    other, _ = company_services.upsert_company(
        organization=organization,
        name="Nothing Matches Ltd",
        website="https://nothing.example",
        industry="Mining",
        country="EG",
        source="test",
    )

    result = score_prospect(other)

    assert result.score == 0
    assert result.band == "low"
    assert "Nothing assessed" in result.reason()


# --------------------------------------------------------------------------- #
# Weighting changes the answer
# --------------------------------------------------------------------------- #


def test_changing_the_weights_changes_the_score(organization: Any, company: Any, icp: ICP) -> None:
    """Section 32's actual requirement, end to end."""
    make_signal(organization, company, signal_type=SignalType.FUNDING, strength=100)

    default_score = score_prospect(company).score

    # A business that only cares about intent, and this company has a perfect
    # intent signal.
    intent_only = {**default_weights(), **dict.fromkeys(ScoreComponent.values, 0)}
    intent_only[ScoreComponent.BUYING_INTENT] = 100
    weighted = score_prospect(company, weights=intent_only)

    assert weighted.score == 100
    assert weighted.score != default_score
    assert weighted.confidence == 100, "the only weighted component was assessable"


def test_a_stored_profile_is_what_scoring_reads(organization: Any, company: Any, icp: ICP) -> None:
    with tenant_context(organization=organization):
        ScoringProfile.objects.create(
            organization=organization, weights={**default_weights(), "icp_fit": 0}
        )

    result = score_prospect(company)

    assert result.weights["icp_fit"] == 0
    assert component(result, ScoreComponent.ICP_FIT).weight == 0


# --------------------------------------------------------------------------- #
# Persistence
# --------------------------------------------------------------------------- #


def test_scoring_a_lead_stores_the_number_and_the_explanation(
    organization: Any, company: Any, icp: ICP
) -> None:
    make_signal(organization, company, signal_type=SignalType.FUNDING, strength=90)
    lead = make_lead(organization, company, icp)

    result = score_lead(lead)
    lead.refresh_from_db()

    assert lead.score == result.score
    assert lead.scored_at is not None
    # Stored whole: the number without its explanation is the thing section 32
    # explicitly forbids.
    assert lead.score_breakdown["band"] == result.band
    assert lead.score_breakdown["components"]
    assert lead.score_breakdown["assumptions"]["weights"]


def test_rescoring_an_organization_covers_every_lead(
    organization: Any, company: Any, icp: ICP
) -> None:
    other, _ = company_services.upsert_company(
        organization=organization, name="Second", website="https://second.example", source="test"
    )
    make_lead(organization, company, icp)
    make_lead(organization, other, icp)

    assert score_organization_leads(organization=organization) == 2


def test_detecting_a_signal_rescores_the_lead(organization: Any, company: Any, icp: ICP) -> None:
    """A score that does not move when its evidence moves looks current and is not.

    Note which way it moves. Before the crawl, three components could not be
    assessed at all, so the score came from ICP fit and geography alone --
    both close to perfect, on a quarter of the weighting. Examining the
    company found a hiring post and, more tellingly, the *absence* of any
    buying intent, and the score fell.

    That is the system working, and it is why confidence is reported beside
    the number: the first score was not a better assessment, it was a thinner
    one. A test asserting the score only ever rises would have been asserting
    a bug.
    """
    from apps.companies.tasks import detect_company_signals
    from apps.intelligence.models import SnapshotStatus, WebsiteSnapshot

    lead = make_lead(organization, company, icp)
    score_lead(lead)
    lead.refresh_from_db()
    thin_score = lead.score
    thin_confidence = lead.score_breakdown["confidence"]

    with tenant_context(organization=organization):
        WebsiteSnapshot.objects.create(
            organization=organization,
            company=company,
            requested_url="https://harmattanfleet.example/careers",
            final_url="https://harmattanfleet.example/careers",
            status=SnapshotStatus.OK,
            headings=["Open roles", "Senior Fleet Manager", "Logistics Analyst"],
            fetched_at=timezone.now(),
        )

    # Celery is eager in tests, so the chained scoring task runs inline.
    detect_company_signals(company.pk)

    lead.refresh_from_db()
    breakdown = lead.score_breakdown

    # The hiring signal the detector just found is cited in the score.
    assert any(entry["signal_type"] == "hiring" for entry in breakdown["evidence"])
    # Three components moved from "cannot assess" to assessed, so this answer
    # covers far more of the weighting than the first one did.
    assert breakdown["confidence"] > thin_confidence
    assert {"buying_intent", "pain_evidence", "company_growth"}.isdisjoint(
        item["component"] for item in breakdown["not_assessed"]
    )
    # And the stored score reflects the fuller picture, not the flattering one.
    assert lead.score != thin_score
    assert lead.scored_at is not None


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #


def test_the_score_endpoint_explains_itself(
    organization: Any,
    owner: Any,
    auth_client: Callable[..., Any],
    company: Any,
    icp: ICP,
) -> None:
    make_signal(organization, company, signal_type=SignalType.FUNDING, strength=90)
    lead = make_lead(organization, company, icp)
    score_lead(lead)

    response = auth_client(owner, organization).get(f"{PROSPECTS_URL}/{company.public_id}/score")

    assert response.status_code == 200
    assert response.data["recommendation"]
    assert response.data["evidence"]
    assert response.data["company"]["name"] == "Harmattan Fleet"
    # Both numbers, because they can differ: the list sorted by the stored
    # one, and a reader should not have to wonder why the panel disagrees.
    assert response.data["stored_score"] == lead.score


def test_rescoring_requires_managing_prospects(
    organization: Any,
    auth_client: Callable[..., Any],
    make_member: Callable[..., Any],
    company: Any,
    icp: ICP,
) -> None:
    lead = make_lead(organization, company, icp)
    url = f"{PROSPECTS_URL}/{company.public_id}/rescore"

    viewer = make_member(organization, role=Role.VIEWER).user
    assert auth_client(viewer, organization).post(url).status_code == 403

    manager = make_member(organization, role=Role.SALES_REP).user
    response = auth_client(manager, organization).post(url)

    assert response.status_code == 200
    lead.refresh_from_db()
    assert lead.scored_at is not None


def test_rescoring_a_company_that_is_not_a_lead_says_why(
    organization: Any, owner: Any, auth_client: Callable[..., Any], company: Any
) -> None:
    """There is nowhere to store a score for a company nobody is pursuing."""
    response = auth_client(owner, organization).post(f"{PROSPECTS_URL}/{company.public_id}/rescore")

    assert response.status_code == 400
    assert "not a lead yet" in str(response.data)


def test_the_weights_endpoint_returns_the_vocabulary_as_well_as_the_values(
    organization: Any, owner: Any, auth_client: Callable[..., Any]
) -> None:
    """So a client can build the form without hardcoding section 32's table."""
    response = auth_client(owner, organization).get(SCORING_URL)

    assert response.status_code == 200
    assert response.data["weights"] == DEFAULT_WEIGHTS
    assert response.data["is_customised"] is False
    components = {item["component"]: item for item in response.data["components"]}
    assert set(components) == set(ScoreComponent.values)
    assert components["icp_fit"]["label"] == "ICP fit"
    assert components["icp_fit"]["default"] == 25


def test_changing_the_weights_is_recorded_and_triggers_a_rescore(
    organization: Any,
    owner: Any,
    auth_client: Callable[..., Any],
    company: Any,
    icp: ICP,
) -> None:
    from apps.audit.models import AuditAction, AuditLog

    make_signal(organization, company, signal_type=SignalType.FUNDING, strength=100)
    lead = make_lead(organization, company, icp)
    score_lead(lead)
    lead.refresh_from_db()
    before = lead.score

    response = auth_client(owner, organization).patch(
        SCORING_URL, {"weights": {"buying_intent": 100, "icp_fit": 0}}, format="json"
    )

    assert response.status_code == 200
    assert response.data["weights"]["buying_intent"] == 100
    assert response.data["is_customised"] is True
    # Partial: a component left out keeps its weight rather than being zeroed.
    assert response.data["weights"]["contact_quality"] == DEFAULT_WEIGHTS["contact_quality"]

    with tenant_context(organization=organization):
        assert AuditLog.objects.filter(action=AuditAction.SCORING_WEIGHTS_CHANGED).exists()

    # Every stored score was computed under the old weighting, so the task
    # runs (eagerly, here) rather than leaving a list sorted by one set of
    # rules and explained by another.
    lead.refresh_from_db()
    assert lead.score != before
    assert lead.score_breakdown["assumptions"]["weights"]["buying_intent"] == 100


def test_an_unknown_component_is_refused(
    organization: Any, owner: Any, auth_client: Callable[..., Any]
) -> None:
    response = auth_client(owner, organization).patch(
        SCORING_URL, {"weights": {"vibes": 100}}, format="json"
    )

    assert response.status_code == 400
    assert "vibes" in str(response.data)


def test_weights_of_all_zero_are_refused(
    organization: Any, owner: Any, auth_client: Callable[..., Any]
) -> None:
    """A score with no weighted components has no meaning to explain."""
    response = auth_client(owner, organization).patch(
        SCORING_URL, {"weights": dict.fromkeys(ScoreComponent.values, 0)}, format="json"
    )

    assert response.status_code == 400


@pytest.mark.security
def test_a_viewer_cannot_change_the_weighting(
    organization: Any, auth_client: Callable[..., Any], make_member: Callable[..., Any]
) -> None:
    viewer = make_member(organization, role=Role.VIEWER).user
    client = auth_client(viewer, organization)

    assert client.get(SCORING_URL).status_code == 200
    assert client.patch(SCORING_URL, {"weights": {"icp_fit": 1}}, format="json").status_code == 403
    assert client.delete(SCORING_URL).status_code == 403


def test_resetting_restores_the_prd_defaults(
    organization: Any, owner: Any, auth_client: Callable[..., Any]
) -> None:
    client = auth_client(owner, organization)
    client.patch(SCORING_URL, {"weights": {"icp_fit": 90}}, format="json")

    response = client.delete(SCORING_URL)

    assert response.status_code == 200
    assert response.data["weights"] == DEFAULT_WEIGHTS
    assert response.data["is_customised"] is False


@pytest.mark.tenancy
def test_weights_and_scores_do_not_cross_tenants(
    organization: Any,
    other_organization: Any,
    owner: Any,
    auth_client: Callable[..., Any],
    make_member: Callable[..., Any],
    company: Any,
) -> None:
    auth_client(owner, organization).patch(SCORING_URL, {"weights": {"icp_fit": 90}}, format="json")

    intruder = make_member(other_organization, role=Role.ADMIN).user
    client = auth_client(intruder, other_organization)

    # The other tenant still sees the defaults, not this organization's.
    assert client.get(SCORING_URL).data["weights"] == DEFAULT_WEIGHTS
    assert client.get(f"{PROSPECTS_URL}/{company.public_id}/score").status_code == 404


def test_a_prospect_row_carries_the_band_and_the_confidence(
    organization: Any,
    owner: Any,
    auth_client: Callable[..., Any],
    company: Any,
    icp: ICP,
) -> None:
    """Both, because 82 from three components is not 82 from eight."""
    make_signal(organization, company, signal_type=SignalType.FUNDING, strength=100)
    score_lead(make_lead(organization, company, icp))

    response = auth_client(owner, organization).get(f"{PROSPECTS_URL}?q=Harmattan")

    row = response.data["results"][0]
    assert row["lead"]["score"] > 0
    assert row["lead"]["band"] in {"high", "medium", "low"}
    assert isinstance(row["lead"]["confidence"], int)


def test_prospects_can_be_filtered_by_score(
    organization: Any,
    owner: Any,
    auth_client: Callable[..., Any],
    company: Any,
    icp: ICP,
) -> None:
    make_signal(organization, company, signal_type=SignalType.FUNDING, strength=100)
    score_lead(make_lead(organization, company, icp))

    weak, _ = company_services.upsert_company(
        organization=organization,
        name="Kano Farms",
        website="https://kanofarms.example",
        industry="Agriculture",
        country="EG",
        source="test",
    )
    score_lead(make_lead(organization, weak, icp))

    client = auth_client(owner, organization)
    names = [row["name"] for row in client.get(f"{PROSPECTS_URL}?min_score=50").data["results"]]

    assert names == ["Harmattan Fleet"]


def test_the_score_endpoint_does_not_need_a_lead(
    organization: Any, owner: Any, auth_client: Callable[..., Any], company: Any, icp: ICP
) -> None:
    """Explaining a score is useful before anyone commits to pursuing it."""
    response = auth_client(owner, organization).get(f"{PROSPECTS_URL}/{company.public_id}/score")

    assert response.status_code == 200
    assert response.data["lead"] is None
    assert response.data["stored_score"] is None
    assert response.data["score"] >= 0


def test_the_context_is_built_in_a_bounded_number_of_queries(
    organization: Any,
    company: Any,
    icp: ICP,
    django_assert_max_num_queries: Any,
) -> None:
    """Scoring runs per lead over a whole workspace, so its cost is the list's."""
    make_signal(organization, company, signal_type=SignalType.FUNDING, strength=90)

    with django_assert_max_num_queries(8):
        build_context(company)
