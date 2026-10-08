"""Tenant-scoped DRF base classes.

This is tenancy layer 2. It filters by ``request.organization`` explicitly and
deliberately does not rely on ``TenantManager``'s automatic scoping, so that a
bug in either layer alone cannot leak data.
"""

from __future__ import annotations

from typing import Any

from django.db.models import QuerySet
from rest_framework import mixins, viewsets
from rest_framework.generics import get_object_or_404

from apps.common.permissions import HasCapability, RequireOrganization
from apps.common.tenancy import tenant_context


class TenantScopedQuerysetMixin:
    """Narrow every queryset to the active organization.

    Subclasses override ``get_base_queryset`` rather than ``get_queryset``, so
    the scoping step cannot be accidentally dropped by a subclass that forgets
    to call ``super()``.
    """

    lookup_field = "public_id"
    lookup_url_kwarg = "public_id"
    queryset: QuerySet | None = None

    def get_base_queryset(self) -> QuerySet:
        queryset = self.queryset
        if queryset is None:
            raise AssertionError(
                f"{type(self).__name__} must set `queryset` or override `get_base_queryset()`."
            )
        # all_objects, then scope explicitly: relying on the contextvar here
        # would make this layer a duplicate of layer 1 rather than a check on it.
        return queryset.model.all_objects.all()

    def get_queryset(self) -> QuerySet:
        organization = getattr(self.request, "organization", None)
        if organization is None:
            # RequireOrganization rejects these before they reach here; the
            # empty queryset is a belt-and-braces guard for any view that
            # forgets the permission class.
            return self.get_base_queryset().none()
        return self.get_base_queryset().filter(organization_id=organization.pk)

    def get_object(self) -> Any:
        queryset = self.filter_queryset(self.get_queryset())
        lookup_value = self.kwargs[self.lookup_url_kwarg or self.lookup_field]
        obj = get_object_or_404(queryset, **{self.lookup_field: lookup_value})
        self.check_object_permissions(self.request, obj)
        return obj


class TenantScopedViewSet(TenantScopedQuerysetMixin, viewsets.ModelViewSet):
    """Full CRUD on a tenant-owned model."""

    permission_classes = [RequireOrganization, HasCapability]
    required_capability: str | None = None
    write_capability: str | None = None

    def perform_create(self, serializer: Any) -> None:
        # The organization is never taken from the payload: a client that sends
        # one is attempting to write into another tenant.
        serializer.save(organization=self.request.organization)

    def initial(self, request: Any, *args: Any, **kwargs: Any) -> None:
        super().initial(request, *args, **kwargs)
        organization = getattr(request, "organization", None)
        if organization is not None:
            # Covers code reached from the view that queries models directly
            # rather than through get_queryset().
            self._tenant_scope = tenant_context(organization=organization)
            self._tenant_scope.__enter__()

    def finalize_response(self, request: Any, response: Any, *args: Any, **kwargs: Any) -> Any:
        scope = getattr(self, "_tenant_scope", None)
        if scope is not None:
            scope.__exit__(None, None, None)
            self._tenant_scope = None
        return super().finalize_response(request, response, *args, **kwargs)


class TenantReadOnlyViewSet(
    TenantScopedQuerysetMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """List and retrieve only."""

    permission_classes = [RequireOrganization, HasCapability]
    required_capability: str | None = None


__all__ = [
    "TenantReadOnlyViewSet",
    "TenantScopedQuerysetMixin",
    "TenantScopedViewSet",
]
