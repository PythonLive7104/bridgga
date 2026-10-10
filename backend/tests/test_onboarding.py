"""The onboarding path (PRD section 25, steps 1-5).

Steps 6 to 9 need mailboxes and campaigns, which are Phase 3. What is testable
now is the thing the wizard is built on: **where a customer has got to is
derived from their records, not counted.**

That is the decision under test here, and nearly every case below is a way the
stored-counter version would have been wrong -- a customer who deletes an ICP,
one who arrives with an analysis still running, one whose site could not be
read, one who finished months ago and is tidying up. A counter has to be
correct at every write to be correct at all; a derivation is correct because
it looks.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from django.utils import timezone

from apps.common.tenancy import tenant_context
from apps.intelligence.models import (
    ICP,
    CompanyProfile,
    CountryProfile,
    MarketRecommendation,
    ProfileStatus,
)
from apps.organizations.onboarding import (
    ANALYSIS,
    CONFIRM,
    MARKETS,
    STEP_ORDER,
    WEBSITE,
    mark_complete,
    onboarding_state,
)
from apps.organizations.onboarding import (
    ICP as ICP_STEP,
)
from apps.organizations.roles import Role

pytestmark = pytest.mark.django_db

ONBOARDING_URL = "/api/v1/onboarding"


def steps_by_key(state: Any) -> dict[str, Any]:
    return {step.key: step for step in state.steps}


def make_profile(organization: Any, **fields: Any) -> CompanyProfile:
    defaults: dict[str, Any] = {
        "website": "https://harmattanfleet.example",
        "company_name": "Harmattan Fleet",
        "status": ProfileStatus.READY,
        "last_analyzed_at": timezone.now(),
    }
    with tenant_context(organization=organization):
        profile, _ = CompanyProfile.objects.update_or_create(
            organization=organization, defaults=defaults | fields
        )
        return profile


def make_icp(organization: Any, *, active: bool = True) -> ICP:
    with tenant_context(organization=organization):
        return ICP.objects.create(
            organization=organization, name="West African haulage", is_active=active
        )


def select_market(organization: Any, icp: Any = None) -> MarketRecommendation:
    country, _ = CountryProfile.objects.get_or_create(
        code="NG", defaults={"name": "Nigeria", "currency": "NGN"}
    )
    with tenant_context(organization=organization):
        return MarketRecommendation.objects.create(
            organization=organization,
            country=country,
            icp=icp,
            fit="high",
            score=90,
            reasoning="Largest market in the region.",
            is_selected=True,
        )


# --------------------------------------------------------------------------- #
# Derivation
# --------------------------------------------------------------------------- #


def test_a_new_organization_starts_at_the_first_unfinished_step(
    make_organization: Callable[..., Any],
) -> None:
    organization = make_organization(name="Nothing Set Up")
    state = onboarding_state(organization)

    assert [step.key for step in state.steps] == list(STEP_ORDER)
    assert state.current == WEBSITE
    assert state.complete is False


def test_a_website_given_at_signup_completes_the_first_step(
    make_organization: Callable[..., Any],
) -> None:
    """It is collected on the create-organization form, so step 1 is often done."""
    organization = make_organization(name="With Site", website="https://harmattanfleet.example")
    state = onboarding_state(organization)

    assert steps_by_key(state)[WEBSITE].state == "done"
    assert state.current == ANALYSIS


def test_a_running_analysis_is_its_own_state(organization: Any) -> None:
    """The thirty seconds that matter most must not read as "not started".

    Step 2 is a crawl and an advanced-tier model call. A wizard that knew only
    done and not-done would show nothing while the customer waits, which is
    exactly when they decide whether this product works.
    """
    make_profile(organization, status=ProfileStatus.ANALYZING, last_analyzed_at=None)
    state = onboarding_state(organization)

    assert steps_by_key(state)[ANALYSIS].state == "running"
    assert state.current == ANALYSIS


def test_a_failed_analysis_says_why(organization: Any) -> None:
    """A dead end needs an explanation, not an unfinished tick."""
    make_profile(
        organization,
        status=ProfileStatus.FAILED,
        analysis_error="The website could not be read.",
        last_analyzed_at=None,
    )
    state = onboarding_state(organization)

    step = steps_by_key(state)[ANALYSIS]
    assert step.state == "failed"
    assert step.detail == "The website could not be read."


def test_confirming_the_profile_advances_to_the_icp(organization: Any) -> None:
    make_profile(organization, status=ProfileStatus.CONFIRMED, confirmed_at=timezone.now())
    state = onboarding_state(organization)

    assert steps_by_key(state)[CONFIRM].state == "done"
    assert state.current == ICP_STEP


def test_an_icp_that_exists_but_is_not_active_does_not_finish_the_step(
    organization: Any,
) -> None:
    """Active is what prospect discovery reads. An inactive draft is not setup."""
    make_profile(organization, status=ProfileStatus.CONFIRMED)
    make_icp(organization, active=False)

    state = onboarding_state(organization)

    assert steps_by_key(state)[ICP_STEP].state == "current"
    # The draft is still named, so the wizard can offer to activate it rather
    # than making somebody generate a second one.
    assert steps_by_key(state)[ICP_STEP].detail == "West African haulage"


def test_selecting_a_market_finishes_the_path(organization: Any) -> None:
    make_profile(organization, status=ProfileStatus.CONFIRMED)
    icp = make_icp(organization)
    select_market(organization, icp)

    state = onboarding_state(organization)

    assert all(step.state == "done" for step in state.steps)
    assert state.complete is True


def test_recommended_but_unselected_markets_are_not_a_finished_step(
    organization: Any,
) -> None:
    """The ranking is the agent's; the selection is the customer's decision."""
    make_profile(organization, status=ProfileStatus.CONFIRMED)
    icp = make_icp(organization)
    market = select_market(organization, icp)
    with tenant_context(organization=organization):
        market.is_selected = False
        market.save(update_fields=["is_selected"])

    state = onboarding_state(organization)

    assert steps_by_key(state)[MARKETS].state == "current"
    assert "1 ranked" in steps_by_key(state)[MARKETS].detail


def test_deleting_an_icp_moves_the_customer_back(organization: Any) -> None:
    """The case a stored counter gets wrong.

    An ``onboarding_step`` column incremented past the ICP would still say
    step 5 after the ICP was deleted, and the wizard would offer market
    recommendations with nothing to base them on.
    """
    make_profile(organization, status=ProfileStatus.CONFIRMED)
    icp = make_icp(organization)
    assert onboarding_state(organization).current == MARKETS

    with tenant_context(organization=organization):
        icp.delete()

    assert onboarding_state(organization).current == ICP_STEP


def test_finishing_once_is_not_undone_by_later_tidying(organization: Any) -> None:
    """The one thing that is stored, and why.

    Derivation answers "what is set up". It cannot answer "have we introduced
    ourselves", and a customer who deletes an ICP six months in is managing
    their own data, not restarting.
    """
    make_profile(organization, status=ProfileStatus.CONFIRMED)
    icp = make_icp(organization)
    select_market(organization, icp)
    mark_complete(organization)

    with tenant_context(organization=organization):
        icp.delete()

    state = onboarding_state(organization)
    assert state.complete is True
    assert state.completed_at is not None
    # Still honest about what is actually missing.
    assert steps_by_key(state)[ICP_STEP].state != "done"


def test_marking_complete_twice_keeps_the_first_timestamp(organization: Any) -> None:
    first = mark_complete(organization).onboarding_completed_at
    second = mark_complete(organization).onboarding_completed_at

    assert first == second


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #


def test_the_endpoint_describes_the_path(
    organization: Any, owner: Any, auth_client: Callable[..., Any]
) -> None:
    make_profile(organization, status=ProfileStatus.CONFIRMED)

    response = auth_client(owner, organization).get(ONBOARDING_URL)

    assert response.status_code == 200
    assert response.data["current"] == "icp"
    assert response.data["complete"] is False
    # The order is the server's to own, so a client never hardcodes it.
    assert response.data["order"] == list(STEP_ORDER)
    assert {step["key"] for step in response.data["steps"]} == set(STEP_ORDER)
    assert all(step["label"] for step in response.data["steps"])


def test_a_customer_may_leave_before_finishing(
    organization: Any, owner: Any, auth_client: Callable[..., Any]
) -> None:
    """Not gated on all five steps, on purpose.

    Somebody who does not want market recommendations should be able to get
    on with the product. A wizard that will not let go is one people learn to
    dread.
    """
    response = auth_client(owner, organization).post(ONBOARDING_URL)

    assert response.status_code == 200
    assert response.data["complete"] is True
    assert response.data["completed_at"] is not None
    # And it still reports honestly what was skipped.
    assert any(step["state"] != "done" for step in response.data["steps"])


@pytest.mark.security
def test_a_viewer_can_see_progress_but_not_end_onboarding(
    organization: Any,
    auth_client: Callable[..., Any],
    make_member: Callable[..., Any],
) -> None:
    viewer = make_member(organization, role=Role.VIEWER).user
    client = auth_client(viewer, organization)

    assert client.get(ONBOARDING_URL).status_code == 200
    assert client.post(ONBOARDING_URL).status_code == 403


@pytest.mark.tenancy
def test_progress_is_read_per_organization(
    organization: Any,
    other_organization: Any,
    make_member: Callable[..., Any],
    auth_client: Callable[..., Any],
) -> None:
    make_profile(organization, status=ProfileStatus.CONFIRMED)
    make_icp(organization)

    intruder = make_member(other_organization, role=Role.ADMIN).user
    response = auth_client(intruder, other_organization).get(ONBOARDING_URL)

    # The other tenant's setup is invisible: this workspace is at step one.
    assert response.data["current"] == WEBSITE
    assert all(step["state"] in {"current", "todo"} for step in response.data["steps"])


def test_reading_progress_is_a_bounded_number_of_queries(
    organization: Any,
    owner: Any,
    auth_client: Callable[..., Any],
    django_assert_max_num_queries: Any,
) -> None:
    """It is polled while the analysis runs, so it must stay cheap."""
    make_profile(organization, status=ProfileStatus.CONFIRMED)
    make_icp(organization)

    with django_assert_max_num_queries(12):
        auth_client(owner, organization).get(ONBOARDING_URL)
