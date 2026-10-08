"""Tenant-aware managers and querysets."""

from __future__ import annotations

from typing import TYPE_CHECKING, Self

from django.db import models

from apps.common import tenancy

if TYPE_CHECKING:
    from apps.organizations.models import Organization, Workspace


class TenantQuerySet(models.QuerySet):
    """Queryset with explicit tenant-narrowing helpers."""

    def for_organization(self, organization: Organization | int) -> Self:
        organization_id = getattr(organization, "pk", organization)
        return self.filter(organization_id=organization_id)

    def for_workspace(self, workspace: Workspace | int) -> Self:
        workspace_id = getattr(workspace, "pk", workspace)
        # Workspace-scoped models also carry organization_id; filtering on the
        # workspace alone is sufficient because a workspace belongs to exactly
        # one organization.
        return self.filter(workspace_id=workspace_id)

    def unscoped(self) -> Self:
        """Opt out of automatic scoping for this queryset only."""
        clone = self._chain()
        clone._bridgga_unscoped = True  # type: ignore[attr-defined]
        return clone


class TenantManager(models.Manager.from_queryset(TenantQuerySet)):  # type: ignore[misc]
    """Default manager that narrows to the active organization.

    When a request is in flight the active organization is always set, so an
    accidental ``Model.objects.all()`` in a view returns only that tenant's
    rows. Outside a request (migrations, shell, admin, cross-tenant jobs) there
    is no active organization and the manager behaves normally -- the tenant
    guarantee for those paths comes from ``unscoped()`` being explicit and from
    the view layer, not from here.
    """

    # Django uses the default manager during migrations and related-object
    # descriptors; auto-filtering those would corrupt them.
    use_in_migrations = False

    def get_queryset(self) -> TenantQuerySet:
        queryset: TenantQuerySet = super().get_queryset()
        if tenancy.is_scope_bypassed():
            return queryset
        organization_id = tenancy.get_active_organization_id()
        if organization_id is None:
            return queryset
        return queryset.filter(organization_id=organization_id)

    def unscoped(self) -> TenantQuerySet:
        """Every row across all tenants. Review each call site."""
        return super().get_queryset()


class AllObjectsManager(models.Manager.from_queryset(TenantQuerySet)):  # type: ignore[misc]
    """Never-filtered manager, exposed as ``all_objects``.

    Kept separate from ``objects`` so that cross-tenant access reads
    differently from ordinary access at the call site.
    """

    def get_queryset(self) -> TenantQuerySet:
        return super().get_queryset()


def tenant_model_classes() -> list[type[models.Model]]:
    """Every concrete installed model that carries an organization FK.

    Discovered from the app registry rather than a hand-maintained list, so a
    new tenant model is covered by the isolation test the moment it is added.
    """
    from django.apps import apps as django_apps

    from apps.common.models import TenantOwnedModel

    discovered: list[type[models.Model]] = []
    for model in django_apps.get_models():
        if model._meta.abstract or model._meta.proxy:
            continue
        if issubclass(model, TenantOwnedModel):
            discovered.append(model)
    return sorted(discovered, key=lambda m: m._meta.label)


def tenant_scope_exempt(model: type[models.Model]) -> bool:
    """True when a model opts out of the generic isolation test.

    Opting out requires an explanation on the model:
    ``tenant_isolation_exempt_reason = "..."``.
    """
    return bool(getattr(model, "tenant_isolation_exempt_reason", ""))


__all__ = [
    "AllObjectsManager",
    "TenantManager",
    "TenantQuerySet",
    "tenant_model_classes",
    "tenant_scope_exempt",
]
