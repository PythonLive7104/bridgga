"""Shared test fixtures."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.common.tenancy import tenant_context, unscoped
from apps.organizations.models import Membership, Organization, Workspace
from apps.organizations.roles import Role

User = get_user_model()


@pytest.fixture
def make_user() -> Callable[..., Any]:
    counter = {"n": 0}

    def _make(email: str | None = None, password: str = "test-pass-phrase-1", **extra: Any) -> Any:
        counter["n"] += 1
        return User.objects.create_user(
            email=email or f"user{counter['n']}@example.test",
            password=password,
            **extra,
        )

    return _make


@pytest.fixture
def make_organization(make_user: Callable[..., Any]) -> Callable[..., Any]:
    counter = {"n": 0}

    def _make(name: str | None = None, owner: Any = None, **extra: Any) -> Organization:
        from apps.organizations.services import create_organization

        counter["n"] += 1
        return create_organization(
            name=name or f"Org {counter['n']}",
            owner=owner or make_user(),
            **extra,
        )

    return _make


@pytest.fixture
def organization(make_organization: Callable[..., Any]) -> Organization:
    return make_organization(name="Acme Logistics", country="NG", default_currency="NGN")


@pytest.fixture
def other_organization(make_organization: Callable[..., Any]) -> Organization:
    """A second tenant. Every isolation test needs one."""
    return make_organization(name="Rival Holdings", country="KE", default_currency="KES")


@pytest.fixture
def owner(organization: Organization) -> Any:
    with unscoped():
        return Membership.all_objects.get(organization=organization, role=Role.OWNER).user


@pytest.fixture
def make_member(make_user: Callable[..., Any]) -> Callable[..., Any]:
    def _make(organization: Organization, role: str = Role.VIEWER, user: Any = None) -> Membership:
        with tenant_context(organization=organization):
            return Membership.objects.create(
                organization=organization,
                user=user or make_user(),
                role=role,
            )

    return _make


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def auth_client() -> Callable[..., APIClient]:
    """Client authenticated as a user, optionally with an active organization.

    The organization is selected exactly as the SPA does it, through the
    ``X-Organization`` header, so tests exercise the real resolution path
    rather than a shortcut.
    """

    def _make(user: Any, organization: Organization | None = None) -> APIClient:
        client = APIClient()
        client.force_authenticate(user=user)
        if organization is not None:
            client.credentials(HTTP_X_ORGANIZATION=str(organization.public_id))
        return client

    return _make


@pytest.fixture
def default_workspace(organization: Organization) -> Workspace:
    with tenant_context(organization=organization):
        return Workspace.objects.get(organization=organization, is_default=True)


@pytest.fixture
def free_plan() -> Any:
    from apps.billing.models import Plan, PlanTier

    return Plan.objects.create(
        tier=PlanTier.FREE,
        name="Free",
        monthly_price_minor=0,
        currency="USD",
        included_credits=50,
        max_seats=2,
        max_workspaces=1,
    )
