"""Prospect discovery (PRD sections 29, 103, 117).

The filter set is section 29's, and the target is section 103's: a normal
search under two seconds.

**Two backends, one interface.** Full-text search and trigram similarity are
Postgres features with no SQLite equivalent, which is the limit ADR 0006
anticipated. Rather than force Postgres on every developer, the text search
dispatches on the connection vendor: real ranked FTS where it is available,
and a plain substring match where it is not. The filters, ordering and
pagination are identical either way, so everything except relevance ranking
behaves the same locally as in production.

That split is honest only if it is visible, so ``search_backend()`` reports
which one answered, the API returns it, and the tests that exercise ranking
are skipped off Postgres rather than quietly asserting weaker behaviour.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from django.db import connection
from django.db.models import Q, QuerySet

from apps.companies.models import Company, CompanyStatus

#: Columns the free-text query searches, in descending order of weight.
SEARCH_FIELDS = ("name", "description", "industry", "city")


def search_backend() -> str:
    return "postgres_fts" if connection.vendor == "postgresql" else "substring"


@dataclass(slots=True)
class ProspectFilters:
    """The section 29 filter set.

    Everything is optional and empty means "no constraint", so a caller can
    pass the whole query string through without checking which parts the user
    actually filled in.
    """

    query: str = ""
    countries: list[str] = field(default_factory=list)
    cities: list[str] = field(default_factory=list)
    industries: list[str] = field(default_factory=list)
    employee_ranges: list[str] = field(default_factory=list)
    revenue_ranges: list[str] = field(default_factory=list)
    business_models: list[str] = field(default_factory=list)
    technologies: list[str] = field(default_factory=list)
    #: Signal types (apps.ai.schemas.SignalType) with a live LeadSignal.
    signals: list[str] = field(default_factory=list)
    #: Only companies whose signal of a listed type was observed in the last
    #: N days.
    signal_within_days: int = 0
    #: Include signals that have expired or been dismissed. Off by default:
    #: a signal that went stale is not a reason to call anybody, which is the
    #: whole point of giving signals an expiry (PRD section 33).
    include_stale_signals: bool = False
    has_contact: bool | None = None
    contactable_only: bool = False
    #: Minimum opportunity score (PRD section 32). Applies to the company's
    #: best-scoring lead: the same company can be a lead under two ICPs, and
    #: a strong fit for one of them is a reason to keep it in the list.
    min_score: int = 0
    founded_after: int | None = None
    founded_before: int | None = None
    include_disqualified: bool = False

    @classmethod
    def from_query_params(cls, params: Any) -> ProspectFilters:
        def many(name: str) -> list[str]:
            # Accept both ?country=NG&country=KE and ?country=NG,KE, because
            # one is what a form posts and the other is what a person types.
            values: list[str] = []
            for raw in params.getlist(name):
                values.extend(part.strip() for part in str(raw).split(",") if part.strip())
            return values

        def flag(name: str) -> bool | None:
            raw = params.get(name)
            if raw is None or raw == "":
                return None
            return str(raw).lower() in {"1", "true", "yes", "on"}

        def number(name: str) -> int | None:
            raw = params.get(name)
            try:
                return int(raw) if raw not in (None, "") else None
            except (TypeError, ValueError):
                return None

        return cls(
            query=(params.get("q") or "").strip(),
            countries=[value.upper() for value in many("country")],
            cities=many("city"),
            industries=many("industry"),
            employee_ranges=many("employee_range"),
            revenue_ranges=many("revenue_range"),
            business_models=many("business_model"),
            technologies=many("technology"),
            signals=many("signal"),
            signal_within_days=number("signal_within_days") or 0,
            include_stale_signals=bool(flag("include_stale_signals")),
            min_score=number("min_score") or 0,
            has_contact=flag("has_contact"),
            contactable_only=bool(flag("contactable")),
            founded_after=number("founded_after"),
            founded_before=number("founded_before"),
            include_disqualified=bool(flag("include_disqualified")),
        )

    def is_empty(self) -> bool:
        return self == ProspectFilters()


def search_companies(
    *, organization: Any, filters: ProspectFilters, queryset: QuerySet | None = None
) -> QuerySet:
    """Apply the section 29 filters, ranked when the database can rank."""
    from apps.common.models import UNSENDABLE_CONTACT_STATUSES

    queryset = queryset if queryset is not None else Company.all_objects.all()
    queryset = queryset.filter(organization_id=organization.pk)

    if not filters.include_disqualified:
        # A merged duplicate is not a prospect, and neither is a company
        # somebody already rejected -- surfacing it again wastes the same half
        # hour a second time.
        queryset = queryset.exclude(
            status__in=[CompanyStatus.DUPLICATE, CompanyStatus.DISQUALIFIED]
        )

    if filters.countries:
        queryset = queryset.filter(country__in=filters.countries)
    if filters.cities:
        queryset = queryset.filter(_any_iexact("city", filters.cities))
    if filters.industries:
        queryset = queryset.filter(_any_icontains("industry", filters.industries))
    if filters.employee_ranges:
        queryset = queryset.filter(employee_range__in=filters.employee_ranges)
    if filters.revenue_ranges:
        queryset = queryset.filter(revenue_range__in=filters.revenue_ranges)
    if filters.business_models:
        queryset = queryset.filter(_any_icontains("business_model", filters.business_models))

    if filters.technologies:
        queryset = queryset.filter(
            technologies__name__in=filters.technologies, technologies__is_current=True
        ).distinct()

    if filters.signals:
        queryset = queryset.filter(_signal_condition(filters)).distinct()

    if filters.founded_after:
        queryset = queryset.filter(founded_year__gte=filters.founded_after)
    if filters.founded_before:
        queryset = queryset.filter(founded_year__lte=filters.founded_before)

    if filters.min_score:
        queryset = queryset.filter(leads__score__gte=filters.min_score).distinct()

    if filters.has_contact is True:
        queryset = queryset.filter(people__isnull=False).distinct()
    elif filters.has_contact is False:
        queryset = queryset.filter(people__isnull=True)

    if filters.contactable_only:
        # Reachable *today*: an address exists and is not one we are forbidden
        # or unwise to send to. The suppression list still applies at send.
        queryset = (
            queryset.filter(
                people__email__gt="",
            )
            .exclude(people__email_status__in=UNSENDABLE_CONTACT_STATUSES)
            .distinct()
        )

    if filters.query:
        queryset = _apply_text_search(queryset, filters.query)
    else:
        queryset = queryset.order_by("name", "id")

    return queryset


def _signal_condition(filters: ProspectFilters) -> Q:
    """Companies carrying a live signal of a requested type.

    Returned as one ``Q`` applied in a single ``filter()`` call on purpose.
    Split across two calls, Django joins the relation twice and the conditions
    stop describing the same row: a company with an expired funding signal and
    a live hiring signal would match "live funding signal", which is a false
    positive a salesperson only discovers in front of the buyer.
    """
    from django.utils import timezone

    condition = Q(signals__signal_type__in=filters.signals)

    if not filters.include_stale_signals:
        condition &= Q(signals__dismissed_at__isnull=True) & Q(
            signals__expires_at__gt=timezone.now()
        )

    if filters.signal_within_days:
        since = timezone.now() - timezone.timedelta(days=filters.signal_within_days)
        # Observation time, which is the event date where one is known and the
        # detection date otherwise. A careers page says a role is open, not
        # when it was posted, so `occurred_at` is legitimately null and
        # comparing it alone would silently drop every hiring signal.
        condition &= Q(signals__occurred_at__gte=since) | (
            Q(signals__occurred_at__isnull=True) & Q(signals__detected_at__gte=since)
        )

    return condition


def _any_iexact(field_name: str, values: list[str]) -> Q:
    condition = Q()
    for value in values:
        condition |= Q(**{f"{field_name}__iexact": value})
    return condition


def _any_icontains(field_name: str, values: list[str]) -> Q:
    condition = Q()
    for value in values:
        condition |= Q(**{f"{field_name}__icontains": value})
    return condition


def _apply_text_search(queryset: QuerySet, query: str) -> QuerySet:
    if connection.vendor != "postgresql":
        # SQLite: substring match across the same columns. Unranked, and
        # knowingly weaker -- it is a development convenience, not the
        # behaviour production has.
        condition = Q()
        for name in SEARCH_FIELDS:
            condition |= Q(**{f"{name}__icontains": query})
        return queryset.filter(condition).order_by("name", "id")

    from django.contrib.postgres.search import (
        SearchQuery,
        SearchRank,
        SearchVector,
        TrigramSimilarity,
    )

    # Weighted so a match on the company's name outranks one buried in its
    # description. Without weights, a company that merely mentions "logistics"
    # ranks beside one called Logistics Ltd.
    vector = (
        SearchVector("name", weight="A")
        + SearchVector("industry", weight="B")
        + SearchVector("city", weight="B")
        + SearchVector("description", weight="C")
    )
    search_query = SearchQuery(query, search_type="websearch")

    ranked = queryset.annotate(
        rank=SearchRank(vector, search_query),
        # Trigram catches what stemming cannot: a misspelling, or a partial
        # name somebody half-remembers. The GIN index added in migration 0003
        # is what keeps it off a sequential scan.
        similarity=TrigramSimilarity("name", query),
    ).filter(Q(rank__gt=0.0) | Q(similarity__gt=0.25))

    return ranked.order_by("-rank", "-similarity", "name", "id")


__all__ = ["SEARCH_FIELDS", "ProspectFilters", "search_backend", "search_companies"]
