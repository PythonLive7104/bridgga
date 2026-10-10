"""The research agent and the reason-to-contact (PRD sections 34 and 35).

Section 35 is one paragraph with one hard constraint in it: "The explanation
must be evidence-based." Everything load-bearing in this file is about making
that a property of the system rather than an instruction in a prompt, because
this is the first agent whose output goes into a message a human sends to
somebody they want to do business with.

So the reason-to-contact is stored as a verifiable claim plus an argument, and
the agent checks the claim against the material it was shown. Most of these
tests are about that check: what it accepts, what it rejects, and -- in one
case that is written down rather than glossed over -- what it cannot catch.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from django.test import override_settings
from django.utils import timezone

from apps.ai.providers.base import AIProviderError
from apps.ai.providers.stub import StubProvider
from apps.ai.schemas import (
    Confidence,
    Evidence,
    PersonalizationPoint,
    ReasonToContact,
    SignalType,
)
from apps.ai.schemas import ProspectResearch as ResearchSchema
from apps.common.tenancy import tenant_context
from apps.companies import services as company_services
from apps.companies.models import LeadSignal
from apps.contacts import services as contact_services
from apps.intelligence import research_agents
from apps.intelligence.models import ICP, ProspectResearch, ResearchStatus
from apps.leads import services as lead_services
from apps.organizations.roles import Role

pytestmark = pytest.mark.django_db

PROSPECTS_URL = "/api/v1/prospects"

#: The quote that appears in the material, verbatim. Several tests turn on
#: whether the agent can find exactly this string back.
DEPOT_QUOTE = "We have opened our second depot in Tamale to serve the north."


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture
def company(organization: Any) -> Any:
    made, _ = company_services.upsert_company(
        organization=organization,
        name="Sahel Distribution",
        website="https://saheldistribution.example",
        industry="Distribution",
        country="GH",
        city="Accra",
        employee_range="51-200",
        description="Dry goods distribution across Ghana and Burkina Faso.",
        source="test",
    )
    return made


@pytest.fixture
def icp(organization: Any) -> ICP:
    with tenant_context(organization=organization):
        return ICP.objects.create(
            organization=organization,
            name="West African haulage operators",
            industries=["Distribution", "Haulage"],
            countries=["NG", "GH"],
            job_titles=["Operations Director", "Fleet Manager"],
            pain_signals=[
                {"type": "expansion", "description": "opening a new depot"},
                {"type": "hiring", "description": "hiring fleet or logistics managers"},
            ],
            is_active=True,
        )


@pytest.fixture
def expansion_signal(organization: Any, company: Any) -> LeadSignal:
    with tenant_context(organization=organization):
        return LeadSignal.objects.create(
            organization=organization,
            company=company,
            signal_type=SignalType.EXPANSION,
            title="Opened a second depot in Tamale",
            fingerprint="depot",
            strength=70,
            detector="ai_website_change",
            source_url="https://saheldistribution.example/news/tamale-depot",
            evidence=[
                {
                    "claim": "They opened a depot in Tamale.",
                    "source_type": "website_page",
                    "source_url": "https://saheldistribution.example/news/tamale-depot",
                    "quote": DEPOT_QUOTE,
                }
            ],
        )


def research_output(**overrides: Any) -> ResearchSchema:
    """A plausible agent output, grounded by default."""
    defaults: dict[str, Any] = {
        "summary": "Sahel Distribution moves dry goods across Ghana.",
        "why_they_may_buy": ["A second depot means more vehicles to account for."],
        "likely_pain": ["Fuel reconciliation across two depots."],
        "possible_use_case": "Track the Tamale fleet and reconcile fuel per route.",
        "suggested_approach": "Open on the Tamale depot, not on the product.",
        "personalization_points": [
            PersonalizationPoint(
                point="Their new Tamale depot",
                why_it_lands="It is recent and specific.",
                source_quote=DEPOT_QUOTE,
            )
        ],
        "decision_maker_titles": ["Operations Director"],
        "reason_to_contact": ReasonToContact(
            observation="Sahel Distribution has opened a second depot in Tamale",
            implication=("your fuel reconciliation could keep the new route honest from the start"),
            evidence=[
                Evidence(
                    claim="They opened a depot in Tamale.",
                    source_type="website_page",
                    source_url="https://saheldistribution.example/news/tamale-depot",
                    quote=DEPOT_QUOTE,
                )
            ],
            confidence=Confidence.HIGH,
        ),
        "confidence": Confidence.HIGH,
        "evidence": [
            Evidence(
                claim="They operate across Ghana.",
                source_type="website_page",
                quote="Dry goods distribution across Ghana and Burkina Faso.",
            )
        ],
        "unknowns": ["Fleet size is not stated."],
    }
    return ResearchSchema(**(defaults | overrides))


def make_lead(organization: Any, company: Any, icp: Any = None, score: int = 0) -> Any:
    source = lead_services.get_or_create_source(
        organization=organization, name="Test", kind="manual"
    )
    lead, _ = lead_services.create_lead(
        organization=organization, company=company, source=source, icp=icp
    )
    if score:
        with tenant_context(organization=organization):
            lead.score = score
            lead.save(update_fields=["score"])
    return lead


# --------------------------------------------------------------------------- #
# The context the agent is given
# --------------------------------------------------------------------------- #


def test_the_prospect_context_carries_the_signal_quotes(
    organization: Any, company: Any, expansion_signal: LeadSignal
) -> None:
    """Without the quotes in the context, a verified reason is impossible.

    The agent checks the reason's evidence against the material it was shown.
    If the quotes behind each signal were summarised away, there would be
    nothing to check against and every reason would be rejected.
    """
    text, signals, _ = research_agents.build_prospect_context(company)

    assert DEPOT_QUOTE in text
    assert "[expansion]" in text
    assert "strength 70/100" in text
    assert signals == [expansion_signal]


def test_the_context_names_contact_roles_but_not_their_details(
    organization: Any, company: Any, expansion_signal: LeadSignal
) -> None:
    """A brief needs to know who to approach, not their email address.

    Section 30 keeps personal contact details under consent rules, and a
    prompt is a place data goes to be copied into other text. The role is what
    the agent needs to suggest an approach.
    """
    contact_services.upsert_person(
        organization=organization,
        company=company,
        email="ama@saheldistribution.example",
        source="test",
        job_title="Operations Director",
        is_decision_maker=True,
    )

    text, _, _ = research_agents.build_prospect_context(company)

    assert "Operations Director" in text
    assert "decision maker" in text
    assert "ama@saheldistribution.example" not in text


def test_the_sellers_own_details_are_sent_as_cacheable_context(
    organization: Any, company: Any, icp: ICP, expansion_signal: LeadSignal
) -> None:
    """It is identical for every prospect, so it is the part caching can reuse.

    Prompt caching is a prefix match: stable content first, volatile content
    last. Sending the seller's profile inside the per-prospect body would mean
    nothing ever caches, at advanced-tier prices.
    """
    provider = StubProvider(responses=[research_output()])

    research_agents.research_company(company=company, icp=icp, provider=provider)

    request = provider.calls[0]
    assert "IDEAL CUSTOMER PROFILE" in request.cacheable_context
    assert "Sahel Distribution" in request.user_content
    # Both halves are externally sourced -- the prospect's website text is in
    # one and the customer's own crawled profile in the other.
    assert "UNTRUSTED CONTENT" in request.user_content


def test_a_company_nobody_knows_anything_about_is_not_researched(
    organization: Any, icp: ICP
) -> None:
    """The cost control. An advanced-tier call to summarise a name is waste."""
    bare, _ = company_services.upsert_company(
        organization=organization, name="Unknown Ltd", source="test"
    )
    provider = StubProvider(responses=[research_output()])

    research = research_agents.research_company(company=bare, icp=icp, provider=provider)

    assert research.status == ResearchStatus.FAILED
    assert "too little known" in research.research_error
    assert provider.calls == []


# --------------------------------------------------------------------------- #
# Verifying the reason-to-contact (section 35)
# --------------------------------------------------------------------------- #


def test_a_grounded_reason_is_stored_with_its_evidence(
    organization: Any, company: Any, icp: ICP, expansion_signal: LeadSignal
) -> None:
    research = research_agents.research_company(
        company=company, icp=icp, provider=StubProvider(responses=[research_output()])
    )

    assert research.has_reason is True
    assert research.reason_observation.startswith("Sahel Distribution has opened")
    assert research.reason_evidence[0]["quote"] == DEPOT_QUOTE
    assert research.reason_confidence == "high"
    assert research.reason_rejected == ""
    # Section 35's own example shape: observation, then implication.
    assert research.reason_sentence == (
        "Sahel Distribution has opened a second depot in Tamale. "
        "Your fuel reconciliation could keep the new route honest from the start"
    )


def test_a_reason_whose_quote_is_not_in_the_material_is_rejected_whole(
    organization: Any, company: Any, icp: ICP, expansion_signal: LeadSignal
) -> None:
    """The check that makes section 35 enforceable rather than aspirational.

    Rejected *whole*, not trimmed: storing the implication without the
    observation would leave a sales argument with nothing behind it, which is
    precisely the free-text flourish the build plan rules out.
    """
    fabricated = research_output(
        reason_to_contact=ReasonToContact(
            observation="Sahel Distribution has just raised a Series B",
            implication="they will be investing in fleet technology",
            evidence=[
                Evidence(
                    claim="They raised a round.",
                    source_type="news",
                    quote="Sahel Distribution has closed a $12M Series B round.",
                )
            ],
            confidence=Confidence.HIGH,
        )
    )

    research = research_agents.research_company(
        company=company, icp=icp, provider=StubProvider(responses=[fabricated])
    )

    assert research.has_reason is False
    assert research.reason_observation == ""
    assert research.reason_implication == ""
    assert research.reason_evidence == []
    # And it says why, because "nothing to say yet" and "the agent made
    # something up" call for different responses from a human.
    assert "could not be found in the source material" in research.reason_rejected
    # The rest of the brief survives: it is judgement, not a claim of fact
    # about the prospect that will be quoted back to them.
    assert research.summary
    assert research.suggested_approach


@pytest.mark.parametrize(
    ("reason", "expected"),
    [
        (None, "did not produce one"),
        (
            ReasonToContact(observation="", implication="they need this", evidence=[]),
            "No observation",
        ),
        (
            ReasonToContact(
                observation="They opened a depot", implication="you can help", evidence=[]
            ),
            "could not be found",
        ),
        (
            ReasonToContact(
                observation="They opened a depot",
                implication="you can help",
                evidence=[Evidence(claim="c", source_type="web", quote="depot")],
            ),
            # Three characters match almost any text and prove nothing.
            "could not be found",
        ),
    ],
)
def test_an_unverifiable_reason_is_refused_with_a_stated_cause(reason: Any, expected: str) -> None:
    verified, why = research_agents.verified_reason(reason, f"...{DEPOT_QUOTE}...")

    assert verified is None
    assert expected in why


def test_a_quote_broken_across_lines_still_counts(organization: Any) -> None:
    """A model reproducing a quote with different wrapping is quoting faithfully."""
    source = "We have opened our second depot\nin Tamale to serve the north."

    assert research_agents.quote_is_grounded(DEPOT_QUOTE, source) is True
    assert research_agents.quote_is_grounded("We have opened our second DEPOT", source) is True
    assert research_agents.quote_is_grounded("opened a depot in Accra", source) is False


@pytest.mark.security
def test_a_quoted_injection_passes_grounding_and_this_is_the_known_limit(
    organization: Any, company: Any, icp: ICP
) -> None:
    """Written down rather than glossed over.

    Grounding proves provenance, not truth. A prospect's website can say
    anything -- including a sentence crafted to be quoted back -- and a quote
    of it will be found in the material, because it *is* in the material.

    What stops this being a hole is everything around it: the quote and its
    source URL are on the card, so the customer reads the claim before using
    it, and the prompt is instructed not to adopt page instructions as facts
    (an eval case covers that). What the code can guarantee is narrower and
    worth being honest about: no claim without a traceable source.
    """
    from apps.intelligence.models import SnapshotStatus, WebsiteSnapshot

    planted = "Sahel Distribution has approved budget for telematics this quarter."
    with tenant_context(organization=organization):
        WebsiteSnapshot.objects.create(
            organization=organization,
            company=company,
            requested_url="https://saheldistribution.example/",
            final_url="https://saheldistribution.example/",
            status=SnapshotStatus.OK,
            text=f"Dry goods distribution across Ghana. {planted}",
            fetched_at=timezone.now(),
        )

    research = research_agents.research_company(
        company=company,
        icp=icp,
        provider=StubProvider(
            responses=[
                research_output(
                    reason_to_contact=ReasonToContact(
                        observation="Sahel Distribution has approved budget for telematics",
                        implication="they are ready to buy",
                        evidence=[
                            Evidence(
                                claim="Stated on their site.",
                                source_type="website_page",
                                quote=planted,
                            )
                        ],
                        confidence=Confidence.HIGH,
                    ),
                    personalization_points=[],
                )
            ]
        ),
    )

    assert research.has_reason is True
    # The mitigation is visibility: the quote is stored, so a human sees the
    # sentence this rests on before repeating it.
    assert research.reason_evidence[0]["quote"] == planted


def test_personalization_points_without_a_real_quote_are_dropped(
    organization: Any, company: Any, icp: ICP, expansion_signal: LeadSignal
) -> None:
    """These go into the message, so they get the same treatment as the reason."""
    output = research_output(
        personalization_points=[
            PersonalizationPoint(point="Their Tamale depot", source_quote=DEPOT_QUOTE),
            PersonalizationPoint(
                point="Their new Lagos office",
                source_quote="We are delighted to open in Lagos this month.",
            ),
            PersonalizationPoint(point="They seem to be growing", source_quote=""),
        ]
    )

    research = research_agents.research_company(
        company=company, icp=icp, provider=StubProvider(responses=[output])
    )

    kept = [point["point"] for point in research.personalization_points]
    assert kept == ["Their Tamale depot"]


def test_evidence_without_a_quote_is_kept_but_a_wrong_quote_is_not(
    organization: Any, company: Any, icp: ICP, expansion_signal: LeadSignal
) -> None:
    """A claim attributed to a page without an excerpt is weaker, not false.

    The URL is still checkable by a human, so dropping it would lose real
    information. A quote that is nowhere in the material is a different thing:
    it asserts the page said something it did not.
    """
    output = research_output(
        evidence=[
            Evidence(claim="They distribute dry goods.", source_type="website_page", quote=""),
            Evidence(
                claim="They run 200 trucks.",
                source_type="website_page",
                quote="Our fleet of 200 trucks covers the whole country.",
            ),
        ]
    )

    research = research_agents.research_company(
        company=company, icp=icp, provider=StubProvider(responses=[output])
    )

    claims = [entry["claim"] for entry in research.evidence]
    assert claims == ["They distribute dry goods."]


# --------------------------------------------------------------------------- #
# The record
# --------------------------------------------------------------------------- #


def test_the_sentence_is_composed_rather_than_stored(organization: Any, company: Any) -> None:
    """Two halves in the database, one sentence on screen.

    Storing the joined string as well would give it two sources of truth, and
    an edit to one half would leave the other stale.
    """
    with tenant_context(organization=organization):
        research = ProspectResearch.objects.create(
            organization=organization,
            company=company,
            reason_observation="They opened a second depot in Tamale.",
            reason_implication="your fuel tooling would pay for itself there",
        )

    assert research.reason_sentence == (
        "They opened a second depot in Tamale. Your fuel tooling would pay for itself there"
    )

    research.reason_implication = ""
    assert research.reason_sentence == "They opened a second depot in Tamale."

    research.reason_observation = ""
    assert research.reason_sentence == ""


def test_the_brief_records_what_it_was_based_on(
    organization: Any, company: Any, icp: ICP, expansion_signal: LeadSignal
) -> None:
    """Provenance (section 61), and the answer to "is this about that signal?"."""
    make_lead(organization, company, icp, score=72)

    research = research_agents.research_company(
        company=company, icp=icp, provider=StubProvider(responses=[research_output()])
    )

    assert research.status == ResearchStatus.READY
    assert research.prompt_pin == "prospect_research@2g2"
    assert research.researched_at is not None
    assert list(research.source_signals.all()) == [expansion_signal]
    # What "high value" meant on the day. The weighting is configurable, so
    # the score alone would not reconstruct the decision later.
    assert research.score_at_research == 72


def test_a_humans_correction_survives_a_re_run(
    organization: Any, company: Any, icp: ICP, expansion_signal: LeadSignal
) -> None:
    """Same rule as every other agent output, and it matters most here.

    A rep who rewrites the approach has done so because they know the account.
    An agent that overwrites it on the next run has made the feature useless.
    """
    research = research_agents.research_company(
        company=company, icp=icp, provider=StubProvider(responses=[research_output()])
    )

    research_agents.apply_edits(
        research=research, data={"suggested_approach": "Call the depot manager directly."}
    )

    research_agents.research_company(
        company=company,
        icp=icp,
        provider=StubProvider(responses=[research_output(suggested_approach="Send an email.")]),
    )
    research.refresh_from_db()

    assert research.suggested_approach == "Call the depot manager directly."
    assert "suggested_approach" in research.edited_fields
    # The agent's version is still there, so the edit is reversible.
    assert research.ai_value_for("suggested_approach") == "Send an email."

    research_agents.reset_fields(research=research, fields=["suggested_approach"])
    research.refresh_from_db()
    assert research.suggested_approach == "Send an email."


def test_an_edited_observation_keeps_the_evidence(
    organization: Any, company: Any, icp: ICP, expansion_signal: LeadSignal
) -> None:
    """Rewording a fact is not unmaking it.

    Clearing the evidence on edit would turn a checkable claim into exactly
    the free-text flourish section 35 forbids -- by way of a helpful feature.
    """
    research = research_agents.research_company(
        company=company, icp=icp, provider=StubProvider(responses=[research_output()])
    )

    research_agents.apply_edits(
        research=research,
        data={"reason_observation": "They have just opened a depot in Tamale"},
    )
    research.refresh_from_db()

    assert research.reason_evidence[0]["quote"] == DEPOT_QUOTE
    assert research.has_reason is True


def test_a_model_failure_is_recorded_not_raised(
    organization: Any, company: Any, icp: ICP, expansion_signal: LeadSignal
) -> None:
    """This runs in a worker; a traceback tells the waiting rep nothing."""
    provider = StubProvider(responses=[AIProviderError("upstream exploded")] * 2)

    research = research_agents.research_company(company=company, icp=icp, provider=provider)

    assert research.status == ResearchStatus.FAILED
    assert "could not be completed" in research.research_error


def test_the_same_company_is_researched_separately_per_icp(
    organization: Any, company: Any, icp: ICP, expansion_signal: LeadSignal
) -> None:
    """What to say to a cold-chain buyer is not what to say to a haulier."""
    with tenant_context(organization=organization):
        second = ICP.objects.create(
            organization=organization, name="Cold-chain distributors", countries=["GH"]
        )

    first_brief = research_agents.research_company(
        company=company, icp=icp, provider=StubProvider(responses=[research_output()])
    )
    second_brief = research_agents.research_company(
        company=company,
        icp=second,
        provider=StubProvider(responses=[research_output(summary="Cold-chain angle.")]),
    )

    assert first_brief.pk != second_brief.pk
    assert ProspectResearch.all_objects.filter(company=company).count() == 2


# --------------------------------------------------------------------------- #
# Who gets researched (section 34: "for high-value prospects")
# --------------------------------------------------------------------------- #


def test_only_high_scoring_prospects_are_researched_automatically(
    organization: Any, company: Any, icp: ICP, monkeypatch: Any
) -> None:
    """An advanced-tier call per company would outprice a whole imported list."""
    from apps.intelligence import tasks

    queued: list[int] = []
    monkeypatch.setattr(
        tasks.research_prospect, "delay", lambda company_id, icp_id=None: queued.append(company_id)
    )

    weak, _ = company_services.upsert_company(
        organization=organization, name="Low Score Ltd", website="https://low.example", source="t"
    )
    make_lead(organization, company, icp, score=80)
    make_lead(organization, weak, icp, score=20)

    assert tasks.research_top_prospects(organization.pk) == 1
    assert queued == [company.pk]


@override_settings(RESEARCH_MIN_SCORE=10)
def test_the_threshold_is_configurable(
    organization: Any, company: Any, icp: ICP, monkeypatch: Any
) -> None:
    from apps.intelligence import tasks

    queued: list[int] = []
    monkeypatch.setattr(
        tasks.research_prospect, "delay", lambda company_id, icp_id=None: queued.append(company_id)
    )
    make_lead(organization, company, icp, score=20)

    assert tasks.research_top_prospects(organization.pk) == 1
    assert queued == [company.pk]


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #


def test_reading_a_brief_that_does_not_exist_says_so(
    organization: Any, owner: Any, auth_client: Callable[..., Any], company: Any
) -> None:
    response = auth_client(owner, organization).get(f"{PROSPECTS_URL}/{company.public_id}/research")

    assert response.status_code == 404
    assert "not been researched" in str(response.data)


def test_the_brief_is_served_with_its_sentence_and_its_evidence(
    organization: Any,
    owner: Any,
    auth_client: Callable[..., Any],
    company: Any,
    icp: ICP,
    expansion_signal: LeadSignal,
) -> None:
    research_agents.research_company(
        company=company, icp=icp, provider=StubProvider(responses=[research_output()])
    )

    response = auth_client(owner, organization).get(f"{PROSPECTS_URL}/{company.public_id}/research")

    assert response.status_code == 200
    assert response.data["reason_sentence"].startswith("Sahel Distribution has opened")
    assert response.data["reason_evidence"][0]["quote"] == DEPOT_QUOTE
    assert response.data["has_reason"] is True
    assert response.data["source_signal_count"] == 1
    assert response.data["personalization_points"][0]["point"] == "Their new Tamale depot"


def test_requesting_research_is_queued_and_needs_manage(
    organization: Any,
    auth_client: Callable[..., Any],
    make_member: Callable[..., Any],
    company: Any,
    monkeypatch: Any,
) -> None:
    """An advanced-tier model call is a spend, so viewing does not grant it."""
    from apps.intelligence import tasks

    queued: list[tuple] = []
    monkeypatch.setattr(
        tasks.research_prospect,
        "delay",
        lambda *args: queued.append(args),
    )
    url = f"{PROSPECTS_URL}/{company.public_id}/research"

    viewer = make_member(organization, role=Role.VIEWER).user
    assert auth_client(viewer, organization).post(url).status_code == 403
    assert queued == []

    manager = make_member(organization, role=Role.SALES_REP).user
    assert auth_client(manager, organization).post(url).status_code == 202
    assert queued and queued[0][0] == company.pk


def test_a_rep_can_correct_the_brief_through_the_api(
    organization: Any,
    owner: Any,
    auth_client: Callable[..., Any],
    company: Any,
    icp: ICP,
    expansion_signal: LeadSignal,
) -> None:
    research_agents.research_company(
        company=company, icp=icp, provider=StubProvider(responses=[research_output()])
    )
    url = f"{PROSPECTS_URL}/{company.public_id}/research"

    response = auth_client(owner, organization).patch(
        url, {"suggested_approach": "Ring the depot."}, format="json"
    )

    assert response.status_code == 200
    assert response.data["suggested_approach"] == "Ring the depot."
    assert response.data["changed_fields"] == ["suggested_approach"]
    assert response.data["fields_meta"]["suggested_approach"]["edited"] is True

    reset = auth_client(owner, organization).post(
        f"{url}/reset", {"fields": ["suggested_approach"]}, format="json"
    )
    assert reset.status_code == 200
    assert reset.data["suggested_approach"] == "Open on the Tamale depot, not on the product."


@pytest.mark.security
def test_a_viewer_cannot_edit_the_brief(
    organization: Any,
    auth_client: Callable[..., Any],
    make_member: Callable[..., Any],
    company: Any,
    icp: ICP,
    expansion_signal: LeadSignal,
) -> None:
    research_agents.research_company(
        company=company, icp=icp, provider=StubProvider(responses=[research_output()])
    )
    viewer = make_member(organization, role=Role.VIEWER).user
    url = f"{PROSPECTS_URL}/{company.public_id}/research"

    assert auth_client(viewer, organization).get(url).status_code == 200
    assert (
        auth_client(viewer, organization)
        .patch(url, {"summary": "nonsense"}, format="json")
        .status_code
        == 403
    )


@pytest.mark.tenancy
def test_another_tenant_cannot_read_a_brief(
    other_organization: Any,
    make_member: Callable[..., Any],
    auth_client: Callable[..., Any],
    organization: Any,
    company: Any,
    icp: ICP,
    expansion_signal: LeadSignal,
) -> None:
    research_agents.research_company(
        company=company, icp=icp, provider=StubProvider(responses=[research_output()])
    )
    intruder = make_member(other_organization, role=Role.ADMIN).user

    response = auth_client(intruder, other_organization).get(
        f"{PROSPECTS_URL}/{company.public_id}/research"
    )

    assert response.status_code == 404


def test_the_prospect_row_carries_the_reason(
    organization: Any,
    owner: Any,
    auth_client: Callable[..., Any],
    company: Any,
    icp: ICP,
    expansion_signal: LeadSignal,
) -> None:
    """The highest-leverage string in the product belongs where it is read."""
    research_agents.research_company(
        company=company, icp=icp, provider=StubProvider(responses=[research_output()])
    )

    response = auth_client(owner, organization).get(f"{PROSPECTS_URL}?q=Sahel")

    row = response.data["results"][0]
    assert row["reason"]["sentence"].startswith("Sahel Distribution has opened")
    assert row["reason"]["evidence_count"] == 1
    assert row["reason"]["rejected"] == ""


def test_a_rejected_reason_is_reported_rather_than_left_blank(
    organization: Any,
    owner: Any,
    auth_client: Callable[..., Any],
    company: Any,
    icp: ICP,
    expansion_signal: LeadSignal,
) -> None:
    """Three different situations must not look identical on a row.

    No research yet, nothing worth saying, and "the agent wrote something we
    could not verify" need different responses from a human, and a blank cell
    tells them apart from nothing.
    """
    research_agents.research_company(
        company=company,
        icp=icp,
        provider=StubProvider(
            responses=[
                research_output(
                    reason_to_contact=ReasonToContact(
                        observation="They just raised a round",
                        implication="they will spend",
                        evidence=[
                            Evidence(
                                claim="A round was raised.",
                                source_type="news",
                                quote="Sahel raised a $12M round last week.",
                            )
                        ],
                    )
                )
            ]
        ),
    )

    response = auth_client(owner, organization).get(f"{PROSPECTS_URL}?q=Sahel")
    reason = response.data["results"][0]["reason"]

    assert reason["sentence"] == ""
    assert "could not be found in the source material" in reason["rejected"]


def test_the_list_does_not_query_per_row_for_the_reason(
    organization: Any,
    owner: Any,
    auth_client: Callable[..., Any],
    icp: ICP,
    django_assert_max_num_queries: Any,
) -> None:
    """Section 103's budget: a column must not cost a query per row."""
    for index in range(8):
        made, _ = company_services.upsert_company(
            organization=organization,
            name=f"Prospect {index}",
            website=f"https://prospect{index}.example",
            source="test",
        )
        with tenant_context(organization=organization):
            ProspectResearch.objects.create(
                organization=organization,
                company=made,
                icp=icp,
                reason_observation=f"Prospect {index} opened a depot",
                reason_implication="you can help",
                reason_evidence=[{"quote": "a quote", "claim": "c"}],
            )

    with django_assert_max_num_queries(12):
        response = auth_client(owner, organization).get(PROSPECTS_URL)

    assert len(response.data["results"]) == 8
    assert all(row["reason"]["sentence"] for row in response.data["results"])
