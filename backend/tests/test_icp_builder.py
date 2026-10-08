"""The ICP builder (PRD section 27).

Section 27 ends with "Allow manual editing", so most of this suite is the same
promise as the company profile: an edit has to survive the next generation and
has to be reversible. That logic is shared (``apps.common.ai_editing``) and
tested once there; what is tested here is what is specific to an ICP --
flattening the buyer profile, the closed signal vocabulary, and the invariant
that exactly one ICP is active.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from apps.ai.providers.stub import StubProvider
from apps.ai.schemas import BuyerProfile, Confidence, ICPDraft, PainSignal, SignalType
from apps.common.tenancy import tenant_context
from apps.intelligence import agents, icp_agents
from apps.intelligence.models import ICP, CompanyProfile, ICPStatus, ProfileStatus
from apps.organizations.roles import Role

pytestmark = pytest.mark.django_db

ICPS_URL = "/api/v1/intelligence/icps"


def draft(**overrides: Any) -> ICPDraft:
    defaults: dict[str, Any] = {
        "name": "African haulage operators",
        "industries": ["logistics", "distribution"],
        "countries": ["Nigeria", "Ghana"],
        "employee_range": "50-500",
        "business_size": "mid-market",
        "growth_stage": "scaling",
        "buyer": BuyerProfile(
            job_titles=["Fleet Manager", "Head of Operations"],
            departments=["Operations"],
            seniority=["manager", "director"],
            responsibilities=["Fleet uptime", "Delivery SLAs"],
        ),
        "pain_signals": [
            PainSignal(
                type=SignalType.HIRING,
                description="Hiring fleet or logistics managers",
                why_it_matters="Fleet growth outpacing their tooling",
            )
        ],
        "rationale": "They sell telematics to fleets, so fleets are the buyer.",
        "confidence": Confidence.HIGH,
    }
    defaults.update(overrides)
    return ICPDraft(**defaults)


@pytest.fixture
def analysed_profile(organization: Any) -> CompanyProfile:
    """A company profile good enough to build an ICP on."""
    profile = agents.get_or_create_profile(organization=organization)
    with tenant_context(organization=organization):
        profile.company_name = "Harmattan Fleet"
        profile.industry = "logistics software"
        profile.products = ["Fleet Live"]
        profile.geographies = ["Nigeria"]
        profile.status = ProfileStatus.CONFIRMED
        profile.save()
    return profile


# --------------------------------------------------------------------------- #
# Prompt input
# --------------------------------------------------------------------------- #


def test_the_profile_is_summarised_for_the_agent(analysed_profile: CompanyProfile) -> None:
    text = icp_agents.describe_profile(analysed_profile)

    assert "Harmattan Fleet" in text
    assert "logistics software" in text
    assert "Fleet Live" in text


def test_admitted_gaps_are_carried_through(
    organization: Any, analysed_profile: CompanyProfile
) -> None:
    """A gap the profile owns up to should not be papered over by the ICP."""
    with tenant_context(organization=organization):
        analysed_profile.unknowns = ["No pricing is published"]
        analysed_profile.save()

    assert "No pricing is published" in icp_agents.describe_profile(analysed_profile)


def test_empty_fields_are_left_out_rather_than_sent_blank(
    organization: Any, analysed_profile: CompanyProfile
) -> None:
    text = icp_agents.describe_profile(analysed_profile)
    assert "Pricing:" not in text


# --------------------------------------------------------------------------- #
# Generation
# --------------------------------------------------------------------------- #


def test_generation_writes_an_icp(organization: Any, analysed_profile: CompanyProfile) -> None:
    icp = icp_agents.generate_icp(
        organization=organization, provider=StubProvider(responses=[draft()])
    )

    assert icp.status == ICPStatus.READY
    assert icp.name == "African haulage operators"
    assert icp.countries == ["Nigeria", "Ghana"]
    assert icp.source_profile_id == analysed_profile.pk


def test_the_buyer_profile_is_flattened_so_each_part_is_editable(
    organization: Any, analysed_profile: CompanyProfile
) -> None:
    """Correcting the job titles must not mean re-accepting the seniority guess."""
    icp = icp_agents.generate_icp(
        organization=organization, provider=StubProvider(responses=[draft()])
    )

    assert icp.job_titles == ["Fleet Manager", "Head of Operations"]
    assert icp.departments == ["Operations"]
    assert icp.seniority == ["manager", "director"]
    assert icp.responsibilities == ["Fleet uptime", "Delivery SLAs"]
    # Each is tracked separately, which is the point of flattening.
    icp_agents.apply_edits(icp=icp, data={"job_titles": ["Logistics Director"]})
    icp.refresh_from_db()
    assert icp.edited_fields == ["job_titles"]


def test_pain_signals_keep_a_type_the_signal_engine_can_match(
    organization: Any, analysed_profile: CompanyProfile
) -> None:
    """Free-text signals can never be matched to a detector (PRD section 33)."""
    icp = icp_agents.generate_icp(
        organization=organization, provider=StubProvider(responses=[draft()])
    )

    assert icp.pain_signals[0]["type"] == "hiring"
    assert icp.signal_types() == ["hiring"]


def test_generation_is_refused_before_the_company_is_analysed(organization: Any) -> None:
    """A bad ICP on a bad profile is two layers of wrong and only one is visible."""
    icp = icp_agents.generate_icp(organization=organization, provider=StubProvider())

    assert icp.status == ICPStatus.FAILED
    assert "website" in icp.generation_error.lower()


def test_a_model_failure_is_reported_not_raised(
    organization: Any, analysed_profile: CompanyProfile
) -> None:
    from apps.ai.providers.base import AIProviderError

    icp = icp_agents.generate_icp(
        organization=organization,
        provider=StubProvider(responses=[AIProviderError("upstream exploded")]),
    )

    assert icp.status == ICPStatus.FAILED
    assert "upstream exploded" in icp.generation_error


def test_the_profile_reaches_the_model_fenced_as_untrusted(
    organization: Any, analysed_profile: CompanyProfile
) -> None:
    """Parts of the profile came off a website; an edit does not launder that."""
    provider = StubProvider(responses=[draft()])

    icp_agents.generate_icp(organization=organization, provider=provider)

    assert "UNTRUSTED CONTENT" in provider.calls[0].user_content


def test_regeneration_preserves_an_edit(
    organization: Any, analysed_profile: CompanyProfile
) -> None:
    icp = icp_agents.generate_icp(
        organization=organization, provider=StubProvider(responses=[draft()])
    )
    icp_agents.apply_edits(icp=icp, data={"countries": ["Kenya"]})

    icp_agents.generate_icp(
        organization=organization,
        icp=icp,
        provider=StubProvider(responses=[draft(countries=["Egypt"])]),
    )

    icp.refresh_from_db()
    assert icp.countries == ["Kenya"]
    assert icp.ai_value_for("countries") == ["Egypt"]


def test_regenerating_an_active_icp_leaves_it_active(
    organization: Any, analysed_profile: CompanyProfile
) -> None:
    """Campaigns and saved searches point at it; deactivating would stop them."""
    icp = icp_agents.generate_icp(
        organization=organization, provider=StubProvider(responses=[draft()])
    )
    icp_agents.activate(icp=icp)

    icp_agents.generate_icp(
        organization=organization, icp=icp, provider=StubProvider(responses=[draft()])
    )

    icp.refresh_from_db()
    assert icp.is_active
    assert icp.status == ICPStatus.ACTIVE


# --------------------------------------------------------------------------- #
# Exactly one active
# --------------------------------------------------------------------------- #


def test_activating_one_icp_stands_the_other_down(organization: Any) -> None:
    with tenant_context(organization=organization):
        first = ICP.objects.create(organization=organization, name="Fleets")
        second = ICP.objects.create(organization=organization, name="Distributors")

    icp_agents.activate(icp=first)
    icp_agents.activate(icp=second)

    first.refresh_from_db()
    second.refresh_from_db()
    assert second.is_active
    assert not first.is_active


def test_the_database_itself_refuses_a_second_active_icp(organization: Any) -> None:
    """A read-then-write check in a service loses a concurrent race; the
    partial unique index does not."""
    from django.db import IntegrityError, transaction

    with tenant_context(organization=organization):
        ICP.objects.create(organization=organization, name="Fleets", is_active=True)
        with pytest.raises(IntegrityError), transaction.atomic():
            ICP.objects.create(organization=organization, name="Distributors", is_active=True)


def test_two_tenants_may_each_have_an_active_icp(
    organization: Any, other_organization: Any
) -> None:
    """The constraint is per organization, not global."""
    with tenant_context(organization=organization):
        ICP.objects.create(organization=organization, name="Ours", is_active=True)
    with tenant_context(organization=other_organization):
        theirs = ICP.objects.create(organization=other_organization, name="Theirs", is_active=True)

    assert theirs.is_active


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #


def test_generate_through_the_api(
    organization: Any,
    owner: Any,
    analysed_profile: CompanyProfile,
    auth_client: Callable[..., Any],
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(
        icp_agents,
        "run_prompt",
        lambda **kwargs: _stub_result(draft()),
    )

    response = auth_client(owner, organization).post(f"{ICPS_URL}/generate", format="json")

    assert response.status_code == 201
    assert response.data["name"] == "African haulage operators"


def test_patch_records_the_edit_rather_than_writing_silently(
    organization: Any, owner: Any, auth_client: Callable[..., Any]
) -> None:
    """Saving the serializer directly would lose the provenance."""
    with tenant_context(organization=organization):
        icp = ICP.objects.create(organization=organization, name="Fleets")

    response = auth_client(owner, organization).patch(
        f"{ICPS_URL}/{icp.public_id}", {"employee_range": "10-50"}, format="json"
    )

    assert response.status_code == 200
    assert response.data["employee_range"] == "10-50"
    assert response.data["fields_meta"]["employee_range"]["edited"] is True


def test_an_unknown_signal_type_is_refused(
    organization: Any, owner: Any, auth_client: Callable[..., Any]
) -> None:
    """It would be accepted, then silently match nothing, much later."""
    with tenant_context(organization=organization):
        icp = ICP.objects.create(organization=organization, name="Fleets")

    response = auth_client(owner, organization).patch(
        f"{ICPS_URL}/{icp.public_id}",
        {"pain_signals": [{"type": "vibes", "description": "feels right"}]},
        format="json",
    )

    assert response.status_code == 400
    assert "vibes" in str(response.data)


def test_a_known_signal_type_is_accepted(
    organization: Any, owner: Any, auth_client: Callable[..., Any]
) -> None:
    with tenant_context(organization=organization):
        icp = ICP.objects.create(organization=organization, name="Fleets")

    response = auth_client(owner, organization).patch(
        f"{ICPS_URL}/{icp.public_id}",
        {"pain_signals": [{"type": "funding", "description": "Raised a Series A"}]},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["pain_signals"][0]["type"] == "funding"


def test_a_signal_without_a_description_is_refused(
    organization: Any, owner: Any, auth_client: Callable[..., Any]
) -> None:
    """A bare type says to watch for hiring, but not what kind of hiring."""
    with tenant_context(organization=organization):
        icp = ICP.objects.create(organization=organization, name="Fleets")

    response = auth_client(owner, organization).patch(
        f"{ICPS_URL}/{icp.public_id}", {"pain_signals": [{"type": "hiring"}]}, format="json"
    )

    assert response.status_code == 400


def test_a_sales_rep_may_read_but_not_edit(
    organization: Any, make_member: Callable[..., Any], auth_client: Callable[..., Any]
) -> None:
    """Changing the ICP changes what the whole workspace targets."""
    with tenant_context(organization=organization):
        icp = ICP.objects.create(organization=organization, name="Fleets")
    rep = make_member(organization, role=Role.SALES_REP)
    client = auth_client(rep.user, organization)

    assert client.get(ICPS_URL).status_code == 200
    assert (
        client.patch(f"{ICPS_URL}/{icp.public_id}", {"name": "Mine"}, format="json").status_code
        == 403
    )


def test_activate_through_the_api(
    organization: Any, owner: Any, auth_client: Callable[..., Any]
) -> None:
    with tenant_context(organization=organization):
        icp = ICP.objects.create(organization=organization, name="Fleets")

    response = auth_client(owner, organization).post(
        f"{ICPS_URL}/{icp.public_id}/activate", format="json"
    )

    assert response.status_code == 200
    assert response.data["is_active"] is True


def test_reset_through_the_api(
    organization: Any, owner: Any, analysed_profile: CompanyProfile, auth_client: Callable[..., Any]
) -> None:
    icp = icp_agents.generate_icp(
        organization=organization, provider=StubProvider(responses=[draft()])
    )
    client = auth_client(owner, organization)
    client.patch(f"{ICPS_URL}/{icp.public_id}", {"employee_range": "1-2"}, format="json")

    response = client.post(
        f"{ICPS_URL}/{icp.public_id}/reset", {"fields": ["employee_range"]}, format="json"
    )

    assert response.status_code == 200
    assert response.data["employee_range"] == "50-500"


def test_one_tenant_never_lists_another_icp(
    organization: Any,
    other_organization: Any,
    owner: Any,
    auth_client: Callable[..., Any],
) -> None:
    with tenant_context(organization=other_organization):
        ICP.objects.create(organization=other_organization, name="Rival segment")

    response = auth_client(owner, organization).get(ICPS_URL)

    assert response.status_code == 200
    assert response.data["results"] == []


def _stub_result(output: Any) -> Any:
    """Minimal stand-in for what ``run_prompt`` returns."""

    class _Job:
        prompt_pin = "icp_draft@2"

    class _Result:
        def __init__(self) -> None:
            self.output = output
            self.job = _Job()

    return _Result()
