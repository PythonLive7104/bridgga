"""The market recommendation engine (PRD sections 28, 70, 71).

The behaviour that matters is the division of labour: facts come from the
seeded country rows, judgement comes from the model, and anything the model
says about a country it was not given is dropped. A recommendation resting on
an invented fact is worse than no recommendation, because it reads exactly the
same as a good one.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from apps.ai.providers.stub import StubProvider
from apps.ai.schemas import (
    Confidence,
    MarketFitBand,
    MarketRecommendations,
)
from apps.ai.schemas import (
    MarketRecommendation as MarketSchema,
)
from apps.common.tenancy import tenant_context
from apps.intelligence import agents, market_agents
from apps.intelligence.icp_models import ICP
from apps.intelligence.models import (
    CountryProfile,
    MarketFit,
    MarketRecommendation,
    ProfileStatus,
)
from apps.organizations.roles import Role

pytestmark = pytest.mark.django_db

MARKETS_URL = "/api/v1/intelligence/markets"


@pytest.fixture
def countries() -> list[CountryProfile]:
    from io import StringIO

    from django.core.management import call_command

    call_command("seed_countries", stdout=StringIO())
    return list(CountryProfile.objects.filter(is_launch_market=True))


@pytest.fixture
def ready_organization(organization: Any) -> Any:
    """A company profile and an ICP, which the engine requires."""
    profile = agents.get_or_create_profile(organization=organization)
    with tenant_context(organization=organization):
        profile.company_name = "Harmattan Fleet"
        profile.industry = "logistics software"
        profile.geographies = ["Nigeria"]
        profile.status = ProfileStatus.CONFIRMED
        profile.save()
        ICP.objects.create(
            organization=organization,
            name="Haulage operators",
            industries=["logistics"],
            countries=["Nigeria"],
            is_active=True,
        )
    return organization


def recommendations(*entries: tuple[str, str, int]) -> MarketRecommendations:
    return MarketRecommendations(
        recommendations=[
            MarketSchema(
                country_code=code,
                fit=MarketFitBand(fit),
                score=score,
                reasoning=f"Reasoning for {code}.",
                factors={"product_fit": "strong"},
                recommended_channels=["email", "whatsapp"],
            )
            for code, fit, score in entries
        ],
        summary="Ranked by fleet density.",
        confidence=Confidence.HIGH,
    )


# --------------------------------------------------------------------------- #
# Seeded facts
# --------------------------------------------------------------------------- #


def test_the_ten_launch_markets_are_seeded(countries: list[CountryProfile]) -> None:
    codes = {country.code for country in countries}
    assert codes == {"NG", "KE", "GH", "ZA", "EG", "RW", "UG", "TZ", "SN", "CI"}


def test_seeding_twice_updates_rather_than_duplicates(countries: list[CountryProfile]) -> None:
    from io import StringIO

    from django.core.management import call_command

    call_command("seed_countries", stdout=StringIO())

    assert CountryProfile.objects.filter(code="NG").count() == 1


def test_currencies_match_the_prd_list(countries: list[CountryProfile]) -> None:
    """PRD section 72 names the initial currencies; the seed must agree."""
    expected = {"NGN", "KES", "GHS", "ZAR", "EGP", "RWF", "UGX", "TZS", "XOF"}
    assert {country.currency for country in countries} == expected


def test_channel_preferences_match_the_ones_the_prd_states(
    countries: list[CountryProfile],
) -> None:
    """Section 70 states Nigeria, Kenya and South Africa explicitly."""
    by_code = {country.code: country for country in countries}
    assert by_code["NG"].channels == ["email", "whatsapp"]
    assert by_code["KE"].channels == ["email", "whatsapp"]
    assert by_code["ZA"].channels == ["email", "linkedin"]


def test_every_country_names_the_law_that_applies(countries: list[CountryProfile]) -> None:
    """A pointer for the legal review PRD section 62 requires, not advice."""
    for country in countries:
        assert country.data_protection_law, f"{country.code} has no statute reference"


def test_the_prompt_summary_carries_the_facts(countries: list[CountryProfile]) -> None:
    summary = CountryProfile.objects.get(code="SN").summary_for_prompt()

    assert "Senegal" in summary
    assert "XOF" in summary
    assert "French" in summary


# --------------------------------------------------------------------------- #
# Generating a ranking
# --------------------------------------------------------------------------- #


def test_a_ranking_is_stored_with_its_reasoning(
    ready_organization: Any, countries: list[CountryProfile]
) -> None:
    """Section 28: every recommendation must explain itself."""
    provider = StubProvider(
        responses=[recommendations(("NG", "high", 92), ("KE", "medium_high", 74))]
    )

    rows = market_agents.recommend_markets(organization=ready_organization, provider=provider)

    assert [row.country.code for row in rows] == ["NG", "KE"]
    assert rows[0].fit == MarketFit.HIGH
    assert rows[0].rank == 1
    assert rows[0].reasoning


def test_the_ranking_is_ordered_by_score_not_by_the_order_returned(
    ready_organization: Any, countries: list[CountryProfile]
) -> None:
    provider = StubProvider(responses=[recommendations(("GH", "medium", 40), ("NG", "high", 95))])

    rows = market_agents.recommend_markets(organization=ready_organization, provider=provider)

    assert [row.country.code for row in rows] == ["NG", "GH"]
    assert rows[0].rank == 1


def test_the_country_facts_are_put_in_front_of_the_model(
    ready_organization: Any, countries: list[CountryProfile]
) -> None:
    """The whole design: facts in, judgement out."""
    provider = StubProvider(responses=[recommendations(("NG", "high", 90))])

    market_agents.recommend_markets(organization=ready_organization, provider=provider)

    sent = provider.calls[0].user_content
    assert "Nigeria (NG)" in sent
    assert "currency NGN" in sent
    assert "Kigali" in sent  # a hub it could not otherwise know to use


def test_a_country_the_model_was_not_given_is_dropped(
    ready_organization: Any, countries: list[CountryProfile]
) -> None:
    """A recommendation for a market with no facts cannot be acted on."""
    provider = StubProvider(responses=[recommendations(("NG", "high", 90), ("ZZ", "high", 88))])

    rows = market_agents.recommend_markets(organization=ready_organization, provider=provider)

    assert [row.country.code for row in rows] == ["NG"]


def test_a_channel_the_country_does_not_support_is_dropped(
    ready_organization: Any, countries: list[CountryProfile]
) -> None:
    """South Africa is email and LinkedIn (section 70); WhatsApp is not offered."""
    provider = StubProvider(responses=[recommendations(("ZA", "high", 90))])

    rows = market_agents.recommend_markets(organization=ready_organization, provider=provider)

    assert rows[0].recommended_channels == ["email"]


def test_rerunning_replaces_the_ranking_rather_than_accumulating(
    ready_organization: Any, countries: list[CountryProfile]
) -> None:
    market_agents.recommend_markets(
        organization=ready_organization,
        provider=StubProvider(responses=[recommendations(("NG", "high", 90))]),
    )
    market_agents.recommend_markets(
        organization=ready_organization,
        provider=StubProvider(responses=[recommendations(("NG", "medium", 50))]),
    )

    with tenant_context(organization=ready_organization):
        rows = list(MarketRecommendation.objects.filter(country__code="NG"))
    assert len(rows) == 1
    assert rows[0].fit == MarketFit.MEDIUM


def test_rerunning_keeps_what_the_customer_chose(
    ready_organization: Any, countries: list[CountryProfile]
) -> None:
    """A selection is a decision; a re-run is advice and must not overrule it."""
    market_agents.recommend_markets(
        organization=ready_organization,
        provider=StubProvider(responses=[recommendations(("NG", "high", 90))]),
    )
    market_agents.set_selected(organization=ready_organization, codes=["NG"])

    market_agents.recommend_markets(
        organization=ready_organization,
        provider=StubProvider(responses=[recommendations(("NG", "medium", 40))]),
    )

    with tenant_context(organization=ready_organization):
        assert MarketRecommendation.objects.get(country__code="NG").is_selected


def test_international_markets_are_excluded_unless_asked_for(
    ready_organization: Any, countries: list[CountryProfile]
) -> None:
    provider = StubProvider(responses=[recommendations(("NG", "high", 90))])

    market_agents.recommend_markets(organization=ready_organization, provider=provider)

    assert "United Kingdom" not in provider.calls[0].user_content


def test_international_markets_are_included_on_request(
    ready_organization: Any, countries: list[CountryProfile]
) -> None:
    """PRD section 6.2: the reverse flow, selling into Africa and out of it."""
    provider = StubProvider(responses=[recommendations(("NG", "high", 90))])

    market_agents.recommend_markets(
        organization=ready_organization, provider=provider, include_international=True
    )

    assert "United Kingdom" in provider.calls[0].user_content


# --------------------------------------------------------------------------- #
# Refusals
# --------------------------------------------------------------------------- #


def test_recommendation_is_refused_before_the_company_is_analysed(
    organization: Any, countries: list[CountryProfile]
) -> None:
    with pytest.raises(market_agents.MarketError, match="website"):
        market_agents.recommend_markets(organization=organization, provider=StubProvider())


def test_recommendation_is_refused_without_an_icp(
    organization: Any, countries: list[CountryProfile]
) -> None:
    profile = agents.get_or_create_profile(organization=organization)
    with tenant_context(organization=organization):
        profile.status = ProfileStatus.CONFIRMED
        profile.company_name = "Harmattan Fleet"
        profile.save()

    with pytest.raises(market_agents.MarketError, match="ICP"):
        market_agents.recommend_markets(organization=organization, provider=StubProvider())


def test_recommendation_is_refused_with_no_countries_seeded(
    ready_organization: Any,
) -> None:
    """Better than silently recommending nothing."""
    with pytest.raises(market_agents.MarketError, match="seed_countries"):
        market_agents.recommend_markets(organization=ready_organization, provider=StubProvider())


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #


def test_countries_are_readable_by_any_member(
    organization: Any,
    make_member: Callable[..., Any],
    auth_client: Callable[..., Any],
    countries: list[CountryProfile],
) -> None:
    viewer = make_member(organization, role=Role.VIEWER)

    response = auth_client(viewer.user, organization).get("/api/v1/intelligence/countries")

    assert response.status_code == 200
    assert response.data["results"]


def test_countries_cannot_be_edited_through_the_api(
    organization: Any,
    owner: Any,
    auth_client: Callable[..., Any],
    countries: list[CountryProfile],
) -> None:
    """They are facts, maintained by the seed command, identical for everyone."""
    response = auth_client(owner, organization).patch(
        "/api/v1/intelligence/countries/NG", {"currency": "XXX"}, format="json"
    )

    assert response.status_code in {403, 405}


def test_selecting_markets_through_the_api(
    ready_organization: Any,
    owner: Any,
    auth_client: Callable[..., Any],
    countries: list[CountryProfile],
) -> None:
    market_agents.recommend_markets(
        organization=ready_organization,
        provider=StubProvider(
            responses=[recommendations(("NG", "high", 90), ("KE", "medium", 50))]
        ),
    )

    response = auth_client(owner, ready_organization).post(
        f"{MARKETS_URL}/select", {"codes": ["NG"]}, format="json"
    )

    assert response.status_code == 200
    selected = {row["country"]["code"]: row["is_selected"] for row in response.data}
    assert selected == {"NG": True, "KE": False}


def test_a_sales_rep_cannot_choose_markets(
    ready_organization: Any,
    make_member: Callable[..., Any],
    auth_client: Callable[..., Any],
    countries: list[CountryProfile],
) -> None:
    rep = make_member(ready_organization, role=Role.SALES_REP)

    response = auth_client(rep.user, ready_organization).post(
        f"{MARKETS_URL}/select", {"codes": ["NG"]}, format="json"
    )

    assert response.status_code == 403


def test_one_tenant_never_sees_another_ranking(
    ready_organization: Any,
    other_organization: Any,
    owner: Any,
    auth_client: Callable[..., Any],
    countries: list[CountryProfile],
) -> None:
    with tenant_context(organization=other_organization):
        MarketRecommendation.objects.create(
            organization=other_organization,
            country=CountryProfile.objects.get(code="KE"),
            fit=MarketFit.HIGH,
            score=99,
            reasoning="Theirs.",
        )

    response = auth_client(owner, ready_organization).get(MARKETS_URL)

    assert response.status_code == 200
    assert response.data["results"] == []
