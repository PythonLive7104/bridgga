"""Cross-tenant isolation (PRD sections 65 and 108).

This module is deliberately generic. It discovers every concrete model that
inherits ``TenantOwnedModel`` from the Django app registry, so a model added in
a later phase is covered the moment it is written -- nobody has to remember to
extend this file.

A model may opt out only by declaring, on the model itself:

    tenant_isolation_exempt_reason = "why this is safe"

which makes the exemption reviewable in the diff that introduces it.
"""

from __future__ import annotations

from typing import Any

import pytest
from django.db import models as django_models
from model_bakery import baker

from apps.common.managers import tenant_model_classes, tenant_scope_exempt
from apps.common.tenancy import tenant_context, unscoped
from apps.organizations.models import Organization, Workspace

pytestmark = [pytest.mark.django_db, pytest.mark.tenancy]


def _covered_models() -> list[type[django_models.Model]]:
    return [m for m in tenant_model_classes() if not tenant_scope_exempt(m)]


def _model_ids() -> list[str]:
    return [m._meta.label for m in _covered_models()]


def _build_row(model: type[django_models.Model], organization: Organization) -> Any:
    """Create one row of ``model`` owned by ``organization``."""
    kwargs: dict[str, Any] = {"organization": organization}

    field_names = {f.name for f in model._meta.get_fields() if hasattr(f, "attname")}
    if "workspace" in field_names:
        # Otherwise bakery would invent a workspace in some other tenant and
        # WorkspaceOwnedModel.save() would rewrite organization to match it.
        kwargs["workspace"] = Workspace.all_objects.filter(
            organization=organization
        ).first() or baker.make(Workspace, organization=organization)

    with unscoped():
        return baker.make(model, **kwargs)


def test_tenant_model_discovery_is_not_empty() -> None:
    """Guards the guard.

    If discovery silently returned nothing, every parameterised test below
    would vacuously pass and the suite would report green while enforcing
    nothing.
    """
    discovered = _covered_models()
    assert discovered, "No tenant-owned models discovered - isolation tests would be vacuous."

    labels = {m._meta.label for m in discovered}
    # Models known to be tenant-owned since Phase 1; a refactor that drops the
    # TenantOwnedModel base from any of them must fail loudly here.
    for expected in {
        "organizations.Workspace",
        "organizations.Membership",
        "organizations.Invitation",
        "audit.AuditLog",
        "billing.Subscription",
        "billing.CreditEntry",
        "billing.UsageRecord",
    }:
        assert expected in labels, f"{expected} is no longer tenant-scoped"


@pytest.mark.parametrize("model", _covered_models(), ids=_model_ids())
def test_default_manager_hides_other_tenants_rows(
    model: type[django_models.Model],
    organization: Organization,
    other_organization: Organization,
) -> None:
    """Org B's queries must not return Org A's rows."""
    row = _build_row(model, organization)

    with tenant_context(organization=other_organization):
        assert not model.objects.filter(pk=row.pk).exists()
        # Org B has rows of its own -- creating an organization bootstraps a
        # workspace, an owner membership and an audit entry -- so the
        # assertion is that none of what it can see belongs to Org A, not
        # that it can see nothing.
        visible_owners = set(model.objects.values_list("organization_id", flat=True))
        assert visible_owners <= {other_organization.pk}

    # Sanity: the row really was created, so the assertions above are
    # meaningful rather than passing because nothing exists.
    with tenant_context(organization=organization):
        assert model.objects.filter(pk=row.pk).exists()


@pytest.mark.parametrize("model", _covered_models(), ids=_model_ids())
def test_other_tenant_cannot_update_or_delete(
    model: type[django_models.Model],
    organization: Organization,
    other_organization: Organization,
) -> None:
    """Writes scoped to Org B must not touch Org A's rows."""
    row = _build_row(model, organization)

    with tenant_context(organization=other_organization):
        assert model.objects.filter(pk=row.pk).delete()[0] == 0
        assert model.objects.filter(pk=row.pk).update(updated_at=row.updated_at) == 0

    with unscoped():
        assert model.all_objects.filter(pk=row.pk).exists(), "Row was destroyed by another tenant"


@pytest.mark.parametrize("model", _covered_models(), ids=_model_ids())
def test_every_tenant_model_has_an_indexed_organization_column(
    model: type[django_models.Model],
) -> None:
    """Scoping every query on an unindexed column would not survive growth."""
    field = model._meta.get_field("organization")
    assert field.db_index or any(
        "organization" in (idx.fields[0] if idx.fields else "") for idx in model._meta.indexes
    ), f"{model._meta.label}.organization needs an index"


def test_unscoped_is_required_to_cross_tenants(
    organization: Organization, other_organization: Organization
) -> None:
    """Crossing tenants has to be spelled out, never implicit."""
    row = _build_row(Workspace, organization)

    with tenant_context(organization=other_organization):
        assert not Workspace.objects.filter(pk=row.pk).exists()
        # The explicit escape hatch, and only it, sees across tenants.
        assert Workspace.objects.unscoped().filter(pk=row.pk).exists()
        with unscoped():
            assert Workspace.objects.filter(pk=row.pk).exists()


def test_nested_tenant_context_cancels_an_enclosing_bypass(
    organization: Organization, other_organization: Organization
) -> None:
    row = _build_row(Workspace, organization)

    with unscoped():
        with tenant_context(organization=other_organization):
            assert not Workspace.objects.filter(pk=row.pk).exists()
        # The bypass is restored when the inner scope exits.
        assert Workspace.objects.filter(pk=row.pk).exists()


def test_tenant_context_is_restored_after_an_exception(organization: Organization) -> None:
    """A failed request must not leave a tenant bound to the thread."""
    from apps.common import tenancy

    assert tenancy.get_active_organization_id() is None
    with pytest.raises(RuntimeError):
        with tenant_context(organization=organization):
            assert tenancy.get_active_organization_id() == organization.pk
            raise RuntimeError("boom")
    assert tenancy.get_active_organization_id() is None
