"""The market recommendation engine (PRD section 28).

Takes a confirmed company profile and an ICP, and ranks the seeded countries
by how good a market each is -- with the reasoning, which section 28 requires
of every recommendation.

The architecture is the point: **facts from the database, judgement from the
model.** Country currencies, languages, channels and statutes come out of
``CountryProfile`` and go *into* the prompt; only the ranking and the reasoning
come back. An agent asked to recall that Senegal uses the CFA franc will answer
confidently whether or not it knows, and a market recommendation built on an
invented fact is worse than none. So anything the model returns about a country
that it was not given is dropped at the boundary.
"""

from __future__ import annotations

from typing import Any

import structlog
from django.db import transaction

from apps.ai.runner import run_prompt
from apps.ai.schemas import MarketRecommendations
from apps.common.tenancy import tenant_context
from apps.intelligence.icp_agents import describe_profile
from apps.intelligence.models import (
    ICP,
    CompanyProfile,
    CountryProfile,
    MarketFit,
    MarketRecommendation,
    ProfileStatus,
)

logger = structlog.get_logger(__name__)


class MarketError(RuntimeError):
    """Raised when there is nothing to recommend from."""


def describe_icp(icp: ICP) -> str:
    """The parts of an ICP that bear on *where* to sell, not who to sell to."""
    lines: list[str] = []

    def add(label: str, value: Any) -> None:
        if isinstance(value, list):
            value = ", ".join(str(item) for item in value)
        if value:
            lines.append(f"{label}: {value}")

    add("ICP", icp.name)
    add("Industries", icp.industries)
    add("Countries already in the ICP", icp.countries)
    add("Employee range", icp.employee_range)
    add("Business size", icp.business_size)
    add("Business models", icp.business_models)
    add("Technologies", icp.technologies)
    add("Growth stage", icp.growth_stage)
    add("Buyer titles", icp.job_titles)
    add("Watching for", [signal.get("type") for signal in icp.pain_signals if signal.get("type")])
    return "\n".join(lines)


def describe_countries(countries: list[CountryProfile]) -> str:
    """The authoritative facts the agent must reason from and not contradict."""
    return "\n".join(f"- {country.summary_for_prompt()}" for country in countries)


def candidate_countries(*, include_international: bool = False) -> list[CountryProfile]:
    queryset = CountryProfile.objects.all()
    if not include_international:
        queryset = queryset.filter(is_launch_market=True)
    return list(queryset.order_by("name"))


def recommend_markets(
    *,
    organization: Any,
    icp: ICP | None = None,
    include_international: bool = False,
    requested_by: Any = None,
    provider: Any = None,
) -> list[MarketRecommendation]:
    """Rank the seeded countries for this organization.

    Raises rather than recording a failure, unlike the company and ICP agents:
    this is invoked from a request the user is waiting on, and there is no
    draft record for a failure to live on.
    """
    with tenant_context(organization=organization):
        profile = CompanyProfile.objects.filter(organization=organization).first()
        if icp is None:
            icp = ICP.objects.filter(organization=organization, is_active=True).first()
            if icp is None:
                icp = ICP.objects.filter(organization=organization).first()

    if profile is None or profile.status == ProfileStatus.DRAFT:
        raise MarketError("Analyse your company website before recommending markets.")
    if icp is None:
        raise MarketError("Create an ICP before recommending markets.")

    countries = candidate_countries(include_international=include_international)
    if not countries:
        raise MarketError("No country profiles are seeded. Run `manage.py seed_countries` first.")

    known = {country.code: country for country in countries}

    result = run_prompt(
        organization=organization,
        prompt="market_recommendation",
        user_content="\n\n".join(
            [
                "COMPANY\n" + describe_profile(profile),
                "IDEAL CUSTOMER\n" + describe_icp(icp),
                "COUNTRIES (authoritative; do not contradict or supplement)\n"
                + describe_countries(countries),
            ]
        ),
        feature="market_recommendation",
        subject=icp,
        requested_by=requested_by,
        provider=provider,
    )

    return _store(
        organization=organization,
        icp=icp,
        output=result.output,
        known=known,
        prompt_pin=result.job.prompt_pin,
    )


@transaction.atomic
def _store(
    *,
    organization: Any,
    icp: ICP,
    output: MarketRecommendations,
    known: dict[str, CountryProfile],
    prompt_pin: str,
) -> list[MarketRecommendation]:
    """Persist the ranking, dropping anything that was not asked about."""
    stored: list[MarketRecommendation] = []
    ignored: list[str] = []

    # Highest score first, so the stored rank is the order a reader sees.
    ranked = sorted(output.recommendations, key=lambda entry: entry.score, reverse=True)

    with tenant_context(organization=organization):
        # A customer's selections are their own decision; carry them across a
        # re-run rather than silently clearing what they picked.
        selected = set(
            MarketRecommendation.objects.filter(
                organization=organization, is_selected=True
            ).values_list("country__code", flat=True)
        )

        for position, entry in enumerate(ranked, start=1):
            code = (entry.country_code or "").strip().upper()
            country = known.get(code)
            if country is None:
                # The model named a country it was not given. Dropped rather
                # than stored: a recommendation for a market the platform has
                # no facts about cannot be acted on or explained.
                ignored.append(code or "<blank>")
                continue

            channels = [
                channel for channel in entry.recommended_channels if channel in country.channels
            ]

            MarketRecommendation.objects.update_or_create(
                organization=organization,
                country=country,
                defaults={
                    "icp": icp,
                    "fit": _fit(entry.fit),
                    "score": entry.score,
                    "rank": position,
                    "reasoning": entry.reasoning,
                    "factors": entry.factors,
                    "recommended_channels": channels,
                    "cautions": entry.cautions,
                    "prompt_pin": prompt_pin,
                    "is_selected": code in selected,
                },
            )

        stored = list(
            MarketRecommendation.objects.filter(organization=organization)
            .select_related("country")
            .order_by("rank")
        )

    if ignored:
        logger.warning(
            "market_recommendation_unknown_countries",
            organization_id=str(organization.public_id),
            codes=ignored,
        )

    logger.info(
        "market_recommendations_stored",
        organization_id=str(organization.public_id),
        count=len(stored),
        prompt=prompt_pin,
    )
    return stored


def _fit(value: Any) -> str:
    """Map the schema's band onto the model's, defaulting to the cautious one."""
    try:
        return MarketFit(str(value)).value
    except ValueError:
        return MarketFit.MEDIUM


@transaction.atomic
def set_selected(*, organization: Any, codes: list[str]) -> list[MarketRecommendation]:
    """Record which markets the customer actually wants to work.

    A recommendation is advice; this is the decision, and everything
    downstream -- prospect discovery, campaign targeting -- reads the decision.
    """
    wanted = {code.strip().upper() for code in codes}

    with tenant_context(organization=organization):
        rows = list(
            MarketRecommendation.objects.filter(organization=organization).select_related("country")
        )
        for row in rows:
            should = row.country.code in wanted
            if row.is_selected != should:
                row.is_selected = should
                row.save(update_fields=["is_selected", "updated_at"])

        return list(
            MarketRecommendation.objects.filter(organization=organization)
            .select_related("country")
            .order_by("rank")
        )


__all__ = [
    "MarketError",
    "candidate_countries",
    "describe_countries",
    "describe_icp",
    "recommend_markets",
    "set_selected",
]
