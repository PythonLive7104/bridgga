"""Shared test fixtures, and the guard that keeps the suite free.

The default run never calls a paid API. That is enforced here rather than left
to discipline, because the failure mode is silent: a test that forgets to pass
a stub provider still passes, just with a charge attached and nothing in the
output to say so.

A test that genuinely needs a real model marks itself ``live_ai`` and is
skipped unless the suite is run with ``--live-ai``.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.common.tenancy import tenant_context, unscoped
from apps.organizations.models import Membership, Organization, Workspace
from apps.organizations.roles import Role

User = get_user_model()


def pytest_addoption(parser: Any) -> None:
    parser.addoption(
        "--live-ai",
        action="store_true",
        default=False,
        help="Run tests marked `live_ai` against the configured provider. This spends money.",
    )


def pytest_collection_modifyitems(config: Any, items: list[Any]) -> None:
    """Skip the live-model tests unless they were asked for by name.

    Opt-in rather than opt-out: a developer who has a key in their environment
    should not discover that fact from their bill.
    """
    if config.getoption("--live-ai"):
        return
    skip = pytest.mark.skip(reason="needs --live-ai (calls a paid API)")
    for item in items:
        if "live_ai" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def _no_accidental_spend(request: Any) -> Iterator[None]:
    """Fail a non-live test that reaches for a real provider.

    ``config.settings.test`` pins ``AI_PROVIDER`` to the stub, so this is the
    second line of defence: it catches a test that overrides the setting, and
    it catches the provider cache carrying a real client in from a live test
    earlier in the session.
    """
    from apps.ai.registry import get_provider, reset_provider_cache

    live = "live_ai" in request.keywords
    reset_provider_cache()
    try:
        if not live:
            name = get_provider().name
            if name != "stub":
                pytest.fail(
                    f"The AI provider resolved to {name!r} in a test that is not marked "
                    "`live_ai`. That is a billed API call. Pass an explicit "
                    "StubProvider, or mark the test `live_ai`."
                )
        yield
    finally:
        reset_provider_cache()


@pytest.fixture
def live_provider() -> Any:
    """The real configured provider, for a ``live_ai`` test.

    Skips rather than fails when no key is present: a contributor without one
    should still be able to run the live suite and see honest skips.
    """
    from django.test import override_settings

    from apps.ai.registry import get_provider, reset_provider_cache

    provider_name = os.environ.get("AI_PROVIDER", "").strip().lower()
    keys = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}

    if provider_name not in keys:
        pytest.skip("Set AI_PROVIDER to openai or anthropic to run the live tests.")
    if not os.environ.get(keys[provider_name]):
        pytest.skip(f"{keys[provider_name]} is not set.")

    reset_provider_cache()
    with override_settings(AI_PROVIDER=provider_name):
        yield get_provider()
    reset_provider_cache()


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
