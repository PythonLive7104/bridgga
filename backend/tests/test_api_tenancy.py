"""Tenancy and authorisation at the HTTP boundary.

The ORM-level guarantees live in ``test_tenant_isolation``. These tests cover
the paths an attacker actually reaches: a forged organization header, a guessed
object id, and a role doing more than it should.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from django.urls import reverse

from apps.common.tenancy import tenant_context, unscoped
from apps.organizations.models import Membership, Organization, Workspace
from apps.organizations.roles import Role

pytestmark = [pytest.mark.django_db, pytest.mark.security]


def _workspace_list_url() -> str:
    return reverse("v1:workspace-list")


def _workspace_detail_url(workspace: Workspace) -> str:
    return reverse("v1:workspace-detail", kwargs={"public_id": workspace.public_id})


# --------------------------------------------------------------------------- #
# Authentication
# --------------------------------------------------------------------------- #


def test_anonymous_cannot_list_workspaces(api_client: Any) -> None:
    response = api_client.get(_workspace_list_url())
    assert response.status_code in {401, 403}


def test_error_envelope_is_uniform(api_client: Any) -> None:
    response = api_client.get(_workspace_list_url())
    body = response.json()
    assert "type" in body
    assert "detail" in body
    assert "request_id" in body


# --------------------------------------------------------------------------- #
# Organization selection
# --------------------------------------------------------------------------- #


def test_request_without_organization_header_is_rejected_for_tenant_endpoints(
    auth_client: Callable[..., Any], owner: Any
) -> None:
    """A user in several organizations must say which one they mean."""
    from apps.organizations.services import create_organization

    create_organization(name="Second Org", owner=owner)

    client = auth_client(owner)  # no X-Organization header
    response = client.get(_workspace_list_url())
    assert response.status_code == 403
    assert response.json()["type"] == "permission_denied"


def test_single_membership_is_resolved_implicitly(
    auth_client: Callable[..., Any], owner: Any
) -> None:
    client = auth_client(owner)
    response = client.get(_workspace_list_url())
    assert response.status_code == 200
    assert len(response.json()["results"]) == 1


def test_malformed_organization_header_is_a_bad_request(
    auth_client: Callable[..., Any], owner: Any
) -> None:
    client = auth_client(owner)
    client.credentials(HTTP_X_ORGANIZATION="not-a-uuid")
    response = client.get(_workspace_list_url())
    assert response.status_code == 400
    assert response.json()["type"] == "invalid_organization"


def test_forged_organization_header_returns_not_found(
    auth_client: Callable[..., Any], owner: Any, other_organization: Organization
) -> None:
    """Selecting a tenant you do not belong to must not confirm it exists."""
    client = auth_client(owner, organization=other_organization)
    response = client.get(_workspace_list_url())
    assert response.status_code == 404
    assert response.json()["type"] == "not_found"


def test_header_selection_does_not_grant_access_after_membership_removal(
    auth_client: Callable[..., Any], owner: Any, organization: Organization
) -> None:
    with unscoped():
        Membership.all_objects.filter(organization=organization, user=owner).update(is_active=False)

    client = auth_client(owner, organization=organization)
    response = client.get(_workspace_list_url())
    assert response.status_code == 404


# --------------------------------------------------------------------------- #
# Cross-tenant object access
# --------------------------------------------------------------------------- #


def test_cannot_retrieve_another_tenants_object_by_id(
    auth_client: Callable[..., Any],
    owner: Any,
    organization: Organization,
    other_organization: Organization,
) -> None:
    """The classic IDOR: a valid id from the wrong tenant."""
    with tenant_context(organization=other_organization):
        foreign = Workspace.objects.get(organization=other_organization, is_default=True)

    client = auth_client(owner, organization=organization)
    response = client.get(_workspace_detail_url(foreign))
    assert response.status_code == 404


def test_cannot_delete_another_tenants_object(
    auth_client: Callable[..., Any],
    owner: Any,
    organization: Organization,
    other_organization: Organization,
) -> None:
    with tenant_context(organization=other_organization):
        foreign = Workspace.objects.create(organization=other_organization, name="Rival Workspace")

    client = auth_client(owner, organization=organization)
    response = client.delete(_workspace_detail_url(foreign))
    assert response.status_code == 404
    with unscoped():
        assert Workspace.all_objects.filter(pk=foreign.pk).exists()


def test_organization_in_payload_cannot_redirect_a_write(
    auth_client: Callable[..., Any],
    owner: Any,
    organization: Organization,
    other_organization: Organization,
) -> None:
    """A client-supplied organization must be ignored, not honoured."""
    client = auth_client(owner, organization=organization)
    response = client.post(
        _workspace_list_url(),
        {"name": "Injected", "organization": str(other_organization.public_id)},
        format="json",
    )
    assert response.status_code == 201

    with unscoped():
        created = Workspace.all_objects.get(name="Injected")
    assert created.organization_id == organization.pk


def test_list_only_returns_the_active_tenants_rows(
    auth_client: Callable[..., Any],
    owner: Any,
    organization: Organization,
    other_organization: Organization,
) -> None:
    with tenant_context(organization=other_organization):
        Workspace.objects.create(organization=other_organization, name="Rival Only")

    client = auth_client(owner, organization=organization)
    response = client.get(_workspace_list_url())
    names = {row["name"] for row in response.json()["results"]}
    assert "Rival Only" not in names


# --------------------------------------------------------------------------- #
# Role capabilities
# --------------------------------------------------------------------------- #


def test_viewer_can_read_but_not_write(
    auth_client: Callable[..., Any],
    make_member: Callable[..., Any],
    organization: Organization,
) -> None:
    membership = make_member(organization, role=Role.VIEWER)
    client = auth_client(membership.user, organization=organization)

    assert client.get(_workspace_list_url()).status_code == 200
    assert client.post(_workspace_list_url(), {"name": "Nope"}, format="json").status_code == 403


def test_sales_rep_cannot_manage_workspaces(
    auth_client: Callable[..., Any],
    make_member: Callable[..., Any],
    organization: Organization,
) -> None:
    membership = make_member(organization, role=Role.SALES_REP)
    client = auth_client(membership.user, organization=organization)
    assert client.post(_workspace_list_url(), {"name": "Nope"}, format="json").status_code == 403


def test_admin_can_manage_workspaces(
    auth_client: Callable[..., Any],
    make_member: Callable[..., Any],
    organization: Organization,
) -> None:
    membership = make_member(organization, role=Role.ADMIN)
    client = auth_client(membership.user, organization=organization)
    response = client.post(_workspace_list_url(), {"name": "Kenya"}, format="json")
    assert response.status_code == 201


def test_viewer_cannot_read_the_audit_log(
    auth_client: Callable[..., Any],
    make_member: Callable[..., Any],
    organization: Organization,
) -> None:
    membership = make_member(organization, role=Role.VIEWER)
    client = auth_client(membership.user, organization=organization)
    assert client.get(reverse("v1:auditlog-list")).status_code == 403


# --------------------------------------------------------------------------- #
# Privilege escalation
# --------------------------------------------------------------------------- #


def test_admin_cannot_promote_a_member_to_owner(
    auth_client: Callable[..., Any],
    make_member: Callable[..., Any],
    organization: Organization,
) -> None:
    admin = make_member(organization, role=Role.ADMIN)
    target = make_member(organization, role=Role.VIEWER)

    client = auth_client(admin.user, organization=organization)
    response = client.patch(
        reverse("v1:membership-detail", kwargs={"public_id": target.public_id}),
        {"role": Role.OWNER},
        format="json",
    )
    assert response.status_code == 400
    target.refresh_from_db()
    assert target.role == Role.VIEWER


def test_admin_cannot_demote_an_owner(
    auth_client: Callable[..., Any],
    make_member: Callable[..., Any],
    organization: Organization,
    owner: Any,
) -> None:
    admin = make_member(organization, role=Role.ADMIN)
    with unscoped():
        owner_membership = Membership.all_objects.get(organization=organization, user=owner)

    client = auth_client(admin.user, organization=organization)
    response = client.patch(
        reverse("v1:membership-detail", kwargs={"public_id": owner_membership.public_id}),
        {"role": Role.VIEWER},
        format="json",
    )
    assert response.status_code == 400
    owner_membership.refresh_from_db()
    assert owner_membership.role == Role.OWNER


def test_nobody_can_change_their_own_role(
    auth_client: Callable[..., Any],
    make_member: Callable[..., Any],
    organization: Organization,
) -> None:
    admin = make_member(organization, role=Role.ADMIN)
    client = auth_client(admin.user, organization=organization)
    response = client.patch(
        reverse("v1:membership-detail", kwargs={"public_id": admin.public_id}),
        {"role": Role.OWNER},
        format="json",
    )
    assert response.status_code == 400


def test_cannot_change_a_role_in_another_tenant(
    auth_client: Callable[..., Any],
    make_member: Callable[..., Any],
    organization: Organization,
    other_organization: Organization,
    owner: Any,
) -> None:
    foreign = make_member(other_organization, role=Role.VIEWER)
    client = auth_client(owner, organization=organization)
    response = client.patch(
        reverse("v1:membership-detail", kwargs={"public_id": foreign.public_id}),
        {"role": Role.ADMIN},
        format="json",
    )
    assert response.status_code == 404
    foreign.refresh_from_db()
    assert foreign.role == Role.VIEWER


def test_owner_cannot_remove_themselves(organization: Organization, owner: Any) -> None:
    from apps.organizations.services import OrganizationError, remove_member

    with unscoped():
        owner_membership = Membership.all_objects.get(organization=organization, user=owner)

    with pytest.raises(OrganizationError, match="cannot remove yourself"):
        remove_member(actor_membership=owner_membership, target_membership=owner_membership)


def test_owner_can_transfer_ownership(
    auth_client: Callable[..., Any],
    make_member: Callable[..., Any],
    organization: Organization,
    owner: Any,
) -> None:
    """Succession must be possible without staff intervention."""
    target = make_member(organization, role=Role.MANAGER)
    client = auth_client(owner, organization=organization)
    response = client.patch(
        reverse("v1:membership-detail", kwargs={"public_id": target.public_id}),
        {"role": Role.OWNER},
        format="json",
    )
    assert response.status_code == 200
    target.refresh_from_db()
    assert target.role == Role.OWNER


def test_demoting_the_last_owner_is_refused(
    organization: Organization, owner: Any, make_member: Callable[..., Any]
) -> None:
    """The invariant holds even for callers that are not the HTTP API.

    Reaching this through the API is impossible today -- only an Owner may act
    on an Owner, and nobody may act on themselves -- so it is asserted at the
    service layer, where a future staff tool or bulk job would hit it.
    """
    from apps.organizations.services import OrganizationError, change_member_role

    second_owner = make_member(organization, role=Role.OWNER)
    with unscoped():
        sole_owner = Membership.all_objects.get(organization=organization, user=owner)
        # Leave exactly one active owner, then try to demote them.
        Membership.all_objects.filter(pk=second_owner.pk).update(is_active=False)
        second_owner.refresh_from_db()

    with pytest.raises(OrganizationError, match="at least one owner"):
        change_member_role(
            actor_membership=second_owner,
            target_membership=sole_owner,
            new_role=Role.VIEWER,
        )
