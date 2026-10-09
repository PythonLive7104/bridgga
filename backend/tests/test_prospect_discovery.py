"""Prospect discovery (PRD sections 29, 103, 117).

Two things are being tested, and they need different treatment.

The **filters** are vendor-neutral and run everywhere. The **ranking** is not:
full-text search and trigram similarity are Postgres features, and the SQLite
fallback is a weaker substring match. Rather than assert whichever behaviour
the local database happens to give, the ranking tests skip off Postgres and
run for real in CI. A test that passes by asserting less is worse than one
that does not run.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from django.db import connection
from django.utils import timezone

from apps.common.models import ContactStatus
from apps.common.tenancy import tenant_context
from apps.companies import services as company_services
from apps.companies.models import CompanyStatus, LeadSignal, SavedSearch
from apps.companies.search import ProspectFilters, search_backend, search_companies
from apps.contacts import services as contact_services
from apps.leads import services as lead_services
from apps.leads.models import SourceKind
from apps.organizations.roles import Role

pytestmark = pytest.mark.django_db

PROSPECTS_URL = "/api/v1/prospects"
SAVED_URL = "/api/v1/saved-searches"

postgres_only = pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason="Full-text ranking and trigram similarity are Postgres features (ADR 0006).",
)


@pytest.fixture
def prospects(organization: Any) -> dict[str, Any]:
    """A small, deliberately varied set to filter against."""
    made = {}
    for key, fields in {
        "harmattan": {
            "website": "https://harmattanfleet.example",
            "name": "Harmattan Fleet",
            "industry": "Logistics software",
            "country": "NG",
            "city": "Lagos",
            "employee_range": "51-200",
            "description": "Telematics for haulage operators across West Africa.",
        },
        "ledger": {
            "website": "https://ledgerlite.example",
            "name": "LedgerLite",
            "industry": "Fintech",
            "country": "KE",
            "city": "Nairobi",
            "employee_range": "11-50",
            "description": "Bookkeeping for small businesses.",
        },
        "savanna": {
            "website": "https://savannafreight.example",
            "name": "Savanna Freight",
            "industry": "Logistics",
            "country": "NG",
            "city": "Abuja",
            "employee_range": "201-500",
            "description": "Cold-chain distribution.",
        },
    }.items():
        company, _ = company_services.upsert_company(
            organization=organization, source="test", **fields
        )
        made[key] = company
    return made


def make_signal(organization: Any, company: Any, **fields: Any) -> LeadSignal:
    """A live buying signal, unless the caller says otherwise.

    The filters are what is under test here, so the signal is created directly
    rather than detected. The detectors that produce one are covered in
    tests/test_signal_engine.py.
    """
    defaults = {
        "signal_type": "hiring",
        "title": "Hiring three fleet supervisors",
        "strength": 70,
        "detector": "test",
        "fingerprint": "test-fingerprint",
    }
    with tenant_context(organization=organization):
        return LeadSignal.objects.create(
            organization=organization, company=company, **(defaults | fields)
        )


def run(organization: Any, **kwargs: Any) -> list[str]:
    results = search_companies(organization=organization, filters=ProspectFilters(**kwargs))
    return [company.name for company in results]


# --------------------------------------------------------------------------- #
# Filters (section 29)
# --------------------------------------------------------------------------- #


def test_no_filters_returns_everything(organization: Any, prospects: dict) -> None:
    assert len(run(organization)) == 3


def test_filter_by_country(organization: Any, prospects: dict) -> None:
    assert set(run(organization, countries=["NG"])) == {"Harmattan Fleet", "Savanna Freight"}


def test_filter_by_several_countries(organization: Any, prospects: dict) -> None:
    assert len(run(organization, countries=["NG", "KE"])) == 3


def test_filter_by_city(organization: Any, prospects: dict) -> None:
    assert run(organization, cities=["lagos"]) == ["Harmattan Fleet"]


def test_industry_matches_on_substring(organization: Any, prospects: dict) -> None:
    """ "Logistics" must find "Logistics software" too, or the filter is a trap."""
    assert set(run(organization, industries=["logistics"])) == {
        "Harmattan Fleet",
        "Savanna Freight",
    }


def test_filter_by_employee_range(organization: Any, prospects: dict) -> None:
    assert run(organization, employee_ranges=["11-50"]) == ["LedgerLite"]


def test_filters_combine(organization: Any, prospects: dict) -> None:
    assert run(organization, countries=["NG"], employee_ranges=["51-200"]) == ["Harmattan Fleet"]


def test_disqualified_and_merged_companies_are_hidden(organization: Any, prospects: dict) -> None:
    """Surfacing a rejected company again wastes the same half hour twice."""
    with tenant_context(organization=organization):
        prospects["ledger"].status = CompanyStatus.DISQUALIFIED
        prospects["ledger"].save(update_fields=["status"])

    assert "LedgerLite" not in run(organization)
    assert "LedgerLite" in run(organization, include_disqualified=True)


def test_filter_by_technology(organization: Any, prospects: dict) -> None:
    company_services.record_technology(
        company=prospects["harmattan"], name="Shopify", source="test"
    )

    assert run(organization, technologies=["Shopify"]) == ["Harmattan Fleet"]


def test_filter_by_signal(organization: Any, prospects: dict) -> None:
    make_signal(organization, prospects["savanna"])

    assert run(organization, signals=["hiring"]) == ["Savanna Freight"]


def test_an_expired_signal_is_not_a_reason_to_call(organization: Any, prospects: dict) -> None:
    """Recency is the point: a funding round from 2022 is history, not intent."""
    make_signal(
        organization,
        prospects["savanna"],
        signal_type="funding",
        title="Series A",
        occurred_at=timezone.now() - timezone.timedelta(days=900),
        expires_at=timezone.now() - timezone.timedelta(days=720),
    )

    assert run(organization, signals=["funding"]) == []
    # Still findable on purpose, for someone researching a company's history.
    assert run(organization, signals=["funding"], include_stale_signals=True) == ["Savanna Freight"]


def test_a_dismissed_signal_stops_matching(organization: Any, prospects: dict) -> None:
    """A person said this was not relevant. The filter has to believe them."""
    signal = make_signal(organization, prospects["savanna"])
    assert run(organization, signals=["hiring"]) == ["Savanna Freight"]

    with tenant_context(organization=organization):
        signal.dismissed_at = timezone.now()
        signal.save(update_fields=["dismissed_at"])

    assert run(organization, signals=["hiring"]) == []


def test_signal_recency_uses_the_detection_date_when_undated(
    organization: Any, prospects: dict
) -> None:
    """A careers page says a role is open, not when it was posted.

    ``occurred_at`` is legitimately null for most hiring signals, so a filter
    that compared only that column would silently match nothing.
    """
    make_signal(
        organization,
        prospects["savanna"],
        occurred_at=None,
        detected_at=timezone.now() - timezone.timedelta(days=3),
    )

    assert run(organization, signals=["hiring"], signal_within_days=7) == ["Savanna Freight"]
    assert run(organization, signals=["hiring"], signal_within_days=1) == []


def test_a_live_signal_of_another_type_does_not_satisfy_the_filter(
    organization: Any, prospects: dict
) -> None:
    """The type and the liveness have to describe the same signal row.

    Applied as two separate filter calls, Django joins the relation twice and
    this company would match "live funding signal" on the strength of having
    an expired funding signal and a live hiring one.
    """
    make_signal(
        organization,
        prospects["savanna"],
        signal_type="funding",
        title="Old round",
        fingerprint="old-funding",
        expires_at=timezone.now() - timezone.timedelta(days=10),
    )
    make_signal(organization, prospects["savanna"], fingerprint="live-hiring")

    assert run(organization, signals=["funding"]) == []
    assert run(organization, signals=["hiring"]) == ["Savanna Freight"]


def test_filter_by_whether_a_contact_is_known(organization: Any, prospects: dict) -> None:
    contact_services.upsert_person(
        organization=organization,
        company=prospects["harmattan"],
        email="ada@harmattanfleet.example",
        source="test",
    )

    assert run(organization, has_contact=True) == ["Harmattan Fleet"]
    assert set(run(organization, has_contact=False)) == {"LedgerLite", "Savanna Freight"}


def test_contactable_excludes_an_unsubscribed_contact(organization: Any, prospects: dict) -> None:
    """The filter has to agree with the send path, or it promises what it cannot do."""
    person, _ = contact_services.upsert_person(
        organization=organization,
        company=prospects["harmattan"],
        email="ada@harmattanfleet.example",
        source="test",
        email_status=ContactStatus.VERIFIED,
    )
    assert run(organization, contactable_only=True) == ["Harmattan Fleet"]

    person.mark_unsubscribed()
    assert run(organization, contactable_only=True) == []


def test_one_tenant_never_searches_another(
    organization: Any, other_organization: Any, prospects: dict
) -> None:
    company_services.upsert_company(
        organization=other_organization, source="test", name="Rival Co", website="https://r.example"
    )

    assert "Rival Co" not in run(organization)


# --------------------------------------------------------------------------- #
# Query parsing
# --------------------------------------------------------------------------- #


def test_repeated_and_comma_separated_parameters_both_work(rf: Any) -> None:
    """A form posts one shape and a person types the other."""
    from django.http import QueryDict

    repeated = QueryDict("country=NG&country=KE")
    commas = QueryDict("country=NG,KE")

    assert ProspectFilters.from_query_params(repeated).countries == ["NG", "KE"]
    assert ProspectFilters.from_query_params(commas).countries == ["NG", "KE"]


def test_country_codes_are_upper_cased() -> None:
    from django.http import QueryDict

    assert ProspectFilters.from_query_params(QueryDict("country=ng")).countries == ["NG"]


def test_a_malformed_number_is_ignored_rather_than_raising() -> None:
    from django.http import QueryDict

    filters = ProspectFilters.from_query_params(QueryDict("founded_after=soon"))

    assert filters.founded_after is None


# --------------------------------------------------------------------------- #
# Text search
# --------------------------------------------------------------------------- #


def test_text_search_finds_by_name_on_any_database(organization: Any, prospects: dict) -> None:
    assert "Harmattan Fleet" in run(organization, query="Harmattan")


def test_text_search_reaches_the_description(organization: Any, prospects: dict) -> None:
    assert "Savanna Freight" in run(organization, query="cold-chain")


@postgres_only
def test_a_name_match_outranks_a_description_match(organization: Any, prospects: dict) -> None:
    """Without weighting, a company that merely mentions the word ranks equally."""
    company_services.upsert_company(
        organization=organization,
        source="test",
        name="Acme Widgets",
        website="https://acme.example",
        description="We sell to logistics companies.",
    )

    names = run(organization, query="logistics")

    assert names.index("Harmattan Fleet") < names.index("Acme Widgets")


@postgres_only
def test_trigram_catches_a_misspelling(organization: Any, prospects: dict) -> None:
    """Stemming cannot do this, and a half-remembered name is the normal case."""
    assert "Harmattan Fleet" in run(organization, query="Harmatan")


def test_the_backend_in_use_is_reported(organization: Any) -> None:
    """The split is only honest if a caller can see which one answered."""
    assert search_backend() in {"postgres_fts", "substring"}


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #


def test_the_prospect_table_carries_the_columns_the_prd_names(
    organization: Any, owner: Any, auth_client: Callable[..., Any], prospects: dict
) -> None:
    source = lead_services.get_or_create_source(
        organization=organization, name="Test", kind=SourceKind.MANUAL
    )
    person, _ = contact_services.upsert_person(
        organization=organization,
        company=prospects["harmattan"],
        email="ada@harmattanfleet.example",
        source="test",
        job_title="Fleet Manager",
        email_status=ContactStatus.VERIFIED,
    )
    lead_services.create_lead(
        organization=organization,
        company=prospects["harmattan"],
        source=source,
        person=person,
    )
    make_signal(organization, prospects["harmattan"], title="Hiring fleet supervisors")

    response = auth_client(owner, organization).get(f"{PROSPECTS_URL}?q=Harmattan")

    assert response.status_code == 200
    row = response.data["results"][0]
    # PRD section 117's columns, assembled server-side.
    assert row["name"] == "Harmattan Fleet"
    assert row["country"] == "NG"
    assert row["industry"]
    assert row["contact"]["job_title"] == "Fleet Manager"
    assert row["contact"]["contactable"] is True
    assert row["signals"][0]["signal_type"] == "hiring"
    assert row["signals"][0]["title"] == "Hiring fleet supervisors"
    assert row["lead"]["status"] == "new"


def test_the_api_returns_rows_in_the_order_the_search_chose(
    organization: Any, owner: Any, auth_client: Callable[..., Any], prospects: dict
) -> None:
    """Pagination must not reorder a ranked result set.

    Cursor pagination imposes its own ordering on whatever queryset it is
    given, because a cursor is only meaningful against an ordering it
    controls -- so it silently replaced the ranking with "newest first". On
    Postgres that meant a text search returned the most recent matches
    instead of the best ones, which is invisible until someone compares the
    list against what they expected to be at the top. With no query the
    ordering is alphabetical, which is assertable on either backend.
    """
    response = auth_client(owner, organization).get(PROSPECTS_URL)

    assert response.status_code == 200
    assert [row["name"] for row in response.data["results"]] == [
        "Harmattan Fleet",
        "LedgerLite",
        "Savanna Freight",
    ]


def test_a_prospect_without_a_contact_or_lead_still_renders(
    organization: Any, owner: Any, auth_client: Callable[..., Any], prospects: dict
) -> None:
    """Most of a fresh list looks like this; nulls must not break the table."""
    response = auth_client(owner, organization).get(f"{PROSPECTS_URL}?q=LedgerLite")

    row = response.data["results"][0]
    assert row["contact"] is None
    assert row["lead"] is None


def test_the_table_does_not_make_a_query_per_row(
    organization: Any, owner: Any, auth_client: Callable[..., Any], prospects: dict
) -> None:
    """Section 103 budgets two seconds; an N+1 spends it on round trips.

    The bound is deliberately loose -- this is guarding against growth
    proportional to the row count, not pinning an exact number that a harmless
    refactor would break.
    """
    from django.test.utils import CaptureQueriesContext

    client = auth_client(owner, organization)
    with CaptureQueriesContext(connection) as captured:
        client.get(PROSPECTS_URL)

    assert len(captured) < 20, f"{len(captured)} queries for 3 prospects"


def test_the_response_states_which_search_backend_answered(
    organization: Any, owner: Any, auth_client: Callable[..., Any], prospects: dict
) -> None:
    response = auth_client(owner, organization).get(PROSPECTS_URL)

    assert response.data["search_backend"] == search_backend()


def test_facets_offer_only_values_that_are_present(
    organization: Any, owner: Any, auth_client: Callable[..., Any], prospects: dict
) -> None:
    """Offering every country on earth when three are represented is unusable."""
    response = auth_client(owner, organization).get(f"{PROSPECTS_URL}/facets")

    assert response.status_code == 200
    countries = {row["value"]: row["count"] for row in response.data["countries"]}
    assert countries == {"NG": 2, "KE": 1}


def test_prospects_are_read_only_through_this_endpoint(
    organization: Any, owner: Any, auth_client: Callable[..., Any]
) -> None:
    response = auth_client(owner, organization).post(PROSPECTS_URL, {"name": "Nope"}, format="json")

    assert response.status_code in {403, 405}


# --------------------------------------------------------------------------- #
# Saved searches
# --------------------------------------------------------------------------- #


def test_a_saved_search_stores_filters_and_runs_them_later(
    organization: Any, owner: Any, auth_client: Callable[..., Any], prospects: dict
) -> None:
    """Stored filters, never stored results: the question stays live."""
    client = auth_client(owner, organization)
    created = client.post(
        SAVED_URL,
        {
            "name": "Nigerian logistics",
            "filters": {"countries": ["NG"], "industries": ["logistics"]},
        },
        format="json",
    )
    assert created.status_code == 201

    # A company that matches is added *after* the search was saved.
    company_services.upsert_company(
        organization=organization,
        source="test",
        name="Later Logistics",
        website="https://later.example",
        industry="Logistics",
        country="NG",
    )

    response = client.get(f"{SAVED_URL}/{created.data['id']}/results")

    assert response.status_code == 200
    assert "Later Logistics" in [row["name"] for row in response.data["results"]]


def test_running_a_saved_search_records_when_and_how_many(
    organization: Any, owner: Any, auth_client: Callable[..., Any], prospects: dict
) -> None:
    client = auth_client(owner, organization)
    created = client.post(SAVED_URL, {"name": "All", "filters": {}}, format="json")

    client.get(f"{SAVED_URL}/{created.data['id']}/results")

    saved = SavedSearch.objects.get(public_id=created.data["id"])
    assert saved.last_run_at is not None
    assert saved.last_result_count == 3


def test_a_saved_search_with_an_obsolete_filter_still_runs(
    organization: Any, owner: Any, auth_client: Callable[..., Any], prospects: dict
) -> None:
    """A filter removed from the product must not break searches saved before."""
    with tenant_context(organization=organization):
        saved = SavedSearch.objects.create(
            organization=organization,
            name="Old",
            filters={"countries": ["NG"], "moon_phase": "waxing"},
        )

    response = auth_client(owner, organization).get(f"{SAVED_URL}/{saved.public_id}/results")

    assert response.status_code == 200
    assert len(response.data["results"]) == 2


def test_a_private_search_is_not_visible_to_a_colleague(
    organization: Any,
    owner: Any,
    make_member: Callable[..., Any],
    auth_client: Callable[..., Any],
) -> None:
    auth_client(owner, organization).post(
        SAVED_URL, {"name": "Mine", "filters": {}, "is_shared": False}, format="json"
    )
    colleague = make_member(organization, role=Role.SALES_REP)

    response = auth_client(colleague.user, organization).get(SAVED_URL)

    assert response.data["results"] == []


def test_a_shared_search_is_visible_to_the_team(
    organization: Any,
    owner: Any,
    make_member: Callable[..., Any],
    auth_client: Callable[..., Any],
) -> None:
    """One definition of a good prospect beats five private approximations."""
    auth_client(owner, organization).post(
        SAVED_URL, {"name": "Ours", "filters": {}, "is_shared": True}, format="json"
    )
    colleague = make_member(organization, role=Role.SALES_REP)

    response = auth_client(colleague.user, organization).get(SAVED_URL)

    assert [row["name"] for row in response.data["results"]] == ["Ours"]


def test_a_viewer_cannot_save_a_search(
    organization: Any, make_member: Callable[..., Any], auth_client: Callable[..., Any]
) -> None:
    viewer = make_member(organization, role=Role.VIEWER)

    response = auth_client(viewer.user, organization).post(
        SAVED_URL, {"name": "Nope", "filters": {}}, format="json"
    )

    assert response.status_code == 403


def test_one_tenant_never_sees_another_saved_search(
    organization: Any,
    other_organization: Any,
    owner: Any,
    auth_client: Callable[..., Any],
) -> None:
    with tenant_context(organization=other_organization):
        SavedSearch.objects.create(
            organization=other_organization, name="Theirs", filters={}, is_shared=True
        )

    response = auth_client(owner, organization).get(SAVED_URL)

    assert response.data["results"] == []
