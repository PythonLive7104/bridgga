"""Active-organization resolution.

This deliberately does *not* live in middleware. Django middleware runs before
DRF authenticates, so a middleware-based resolver only ever sees the user that
``AuthenticationMiddleware`` established from the session. Any DRF-level
authentication scheme -- API keys and signed service tokens in Phase 7, or
``force_authenticate`` in tests -- authenticates inside the view, by which time
middleware has already run and concluded the caller was anonymous.

Resolving here, from the DRF permission layer, means one code path works for
every authentication scheme.

The ``X-Organization`` header only *selects*. Authorisation comes from an
active ``Membership``, which is re-read from the database on every request, so
forging the header gains nothing and a revoked membership takes effect at once.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import structlog
from rest_framework import status
from rest_framework.exceptions import APIException, NotFound

if TYPE_CHECKING:
    from apps.organizations.models import Membership

logger = structlog.get_logger(__name__)

_CACHE_ATTR = "_bridgga_tenant_resolved"


class InvalidOrganizationHeader(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "invalid_organization"
    default_detail = "X-Organization must be an organization public id."


class OrganizationSuspended(APIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_code = "organization_suspended"
    default_detail = "This organization is suspended."


def resolve_tenant(request: Any) -> Membership | None:
    """Return the caller's active membership, or None if there is no tenant.

    Raises for a request that names a tenant badly or names one it cannot
    reach. Returns None, without raising, when no tenant could be selected --
    a user with no organizations yet, or one who belongs to several and has not
    chosen. Endpoints that need a tenant reject that case via
    ``RequireOrganization``; ``/me`` tolerates it.

    The result is cached on the request: permissions, the viewset and the view
    body all ask for it.
    """
    from django.conf import settings

    from apps.organizations.models import Membership

    if hasattr(request, _CACHE_ATTR):
        return getattr(request, _CACHE_ATTR)

    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return _cache(request, None)

    requested = _requested_organization_id(request, settings.ORGANIZATION_HEADER)

    # all_objects: Membership is itself tenant-owned and there is no active
    # tenant yet -- this query is what establishes one. The constraint that
    # makes it safe is user=, not the tenant scope.
    memberships = Membership.all_objects.filter(user=user, is_active=True).select_related(
        "organization"
    )

    if requested is not None:
        membership = memberships.filter(organization__public_id=requested).first()
        if membership is None:
            # 404 rather than 403: a 403 would confirm that an organization
            # with that id exists, which leaks the existence of other tenants.
            raise NotFound("Organization not found.")
        if not membership.organization.is_active:
            raise OrganizationSuspended
        return _cache(request, membership)

    # No header. One membership resolves implicitly; several must be chosen
    # between, because guessing would write data into the wrong tenant.
    candidates = list(memberships[:2])
    if len(candidates) == 1:
        return _cache(request, candidates[0])
    return _cache(request, None)


def _requested_organization_id(request: Any, header: str) -> str | None:
    raw = (request.headers.get(header) or "").strip()
    if not raw:
        return None
    try:
        return str(uuid.UUID(raw))
    except ValueError as exc:
        raise InvalidOrganizationHeader from exc


def _cache(request: Any, membership: Membership | None) -> Membership | None:
    setattr(request, _CACHE_ATTR, membership)

    organization = membership.organization if membership is not None else None
    # Written onto the underlying HttpRequest as well as the DRF Request, so
    # that code reached from either sees the same tenant.
    for target in {request, getattr(request, "_request", None)}:
        if target is None:
            continue
        target.organization = organization
        target.membership = membership

    if membership is not None:
        structlog.contextvars.bind_contextvars(
            organization_id=str(organization.public_id),
            role=membership.role,
        )
    return membership
