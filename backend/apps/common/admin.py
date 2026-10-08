"""Admin base classes.

The internal admin (PRD section 75) is a cross-tenant tool, but staff users can
also be members of an organization. Because ``TenantManager`` narrows to the
active organization and the middleware sets one for any user with a membership,
a plain ``ModelAdmin`` would silently show such a staff user only their own
tenant's rows. These bases query ``all_objects`` so the admin always means
"every tenant".
"""

from __future__ import annotations

from typing import Any

from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest


class UnscopedModelAdmin(admin.ModelAdmin):
    """ModelAdmin that deliberately ignores tenant scoping."""

    def get_queryset(self, request: HttpRequest) -> QuerySet:
        manager = getattr(self.model, "all_objects", self.model._default_manager)
        queryset = manager.get_queryset()
        ordering = self.get_ordering(request)
        if ordering:
            queryset = queryset.order_by(*ordering)
        return queryset


class ReadOnlyModelAdmin(UnscopedModelAdmin):
    """For append-only tables. An audit trail staff can edit is not evidence."""

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False
