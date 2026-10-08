"""DRF permission classes.

Views declare what they need rather than checking roles inline:

    class CampaignViewSet(TenantScopedViewSet):
        required_capability = Capability.CAMPAIGN_VIEW
        write_capability = Capability.CAMPAIGN_MANAGE
"""

from __future__ import annotations

from typing import Any

from rest_framework import permissions
from rest_framework.request import Request
from rest_framework.views import APIView

SAFE_METHODS = frozenset(permissions.SAFE_METHODS)


class RequireOrganization(permissions.BasePermission):
    """Resolve the active organization and reject the request if there is none.

    Listed first in ``permission_classes`` so that every later permission and
    the view body can rely on ``request.organization`` being populated. DRF
    evaluates permissions in order and stops at the first denial.
    """

    message = (
        "No active organization. Send the organization's public id in the X-Organization header."
    )

    def has_permission(self, request: Request, view: APIView) -> bool:
        from apps.common.tenant_resolution import resolve_tenant

        return resolve_tenant(request) is not None


class HasCapability(permissions.BasePermission):
    """Check the view's declared capability against the caller's role.

    ``required_capability`` guards reads; ``write_capability``, when set,
    guards anything that mutates. A view that declares neither is denied
    rather than allowed, so forgetting to declare one fails closed.
    """

    def has_permission(self, request: Request, view: APIView) -> bool:
        membership = getattr(request, "membership", None)
        if membership is None:
            return False

        capability = self._capability_for(request, view)
        if capability is None:
            return False
        return membership.has_capability(capability)

    def has_object_permission(self, request: Request, view: APIView, obj: Any) -> bool:
        # Object-level tenancy is re-checked here even though the queryset is
        # already scoped, because a view may fetch an object by another route
        # (PRD section 108: broken object-level authorisation).
        organization = getattr(request, "organization", None)
        if organization is None:
            return False
        obj_org_id = getattr(obj, "organization_id", None)
        if obj_org_id is not None and obj_org_id != organization.pk:
            return False
        return self.has_permission(request, view)

    @staticmethod
    def _capability_for(request: Request, view: APIView) -> str | None:
        read_capability = getattr(view, "required_capability", None)
        write_capability = getattr(view, "write_capability", None)
        if request.method in SAFE_METHODS:
            return read_capability
        return write_capability or read_capability

    def get_message(self, view: APIView) -> str:
        return f"Your role does not grant {getattr(view, 'required_capability', 'this action')}."


class IsOrganizationOwner(permissions.BasePermission):
    """Owner-only actions: deleting the organization, changing the plan."""

    message = "Only the organization owner can perform this action."

    def has_permission(self, request: Request, view: APIView) -> bool:
        from apps.organizations.roles import Role

        membership = getattr(request, "membership", None)
        return membership is not None and membership.role == Role.OWNER


class IsSelfOrHasCapability(HasCapability):
    """Allow a user to act on their own record, else require the capability."""

    def has_object_permission(self, request: Request, view: APIView, obj: Any) -> bool:
        if getattr(obj, "user_id", None) == request.user.pk:
            return True
        return super().has_object_permission(request, view, obj)


__all__ = [
    "HasCapability",
    "IsOrganizationOwner",
    "IsSelfOrHasCapability",
    "RequireOrganization",
]
