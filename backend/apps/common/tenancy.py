"""Active-tenant context.

Tenant scoping is enforced in three independent layers, because any single
layer will eventually be forgotten:

1. This context variable, set by ``CurrentOrganizationMiddleware`` and read by
   ``TenantManager``, so a bare ``Model.objects.all()`` inside a request is
   already scoped.
2. ``TenantScopedViewSet``, which filters by ``request.organization``
   explicitly and never trusts layer 1.
3. ``test_tenant_isolation``, which walks every registered tenant model and
   fails the build if either layer stops working for a newly added model.

Escaping the scope is possible but has to be spelled out: ``unscoped()``.
That makes a leak a visible, reviewable line of code rather than an omission.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.organizations.models import Organization, Workspace

_active_organization_id: ContextVar[int | None] = ContextVar(
    "palatial_active_organization_id", default=None
)
_active_workspace_id: ContextVar[int | None] = ContextVar(
    "palatial_active_workspace_id", default=None
)
_scope_bypassed: ContextVar[bool] = ContextVar("palatial_scope_bypassed", default=False)


class TenantScopeError(RuntimeError):
    """Raised when a tenant-scoped operation has no tenant to scope to."""


def get_active_organization_id() -> int | None:
    return _active_organization_id.get()


def get_active_workspace_id() -> int | None:
    return _active_workspace_id.get()


def is_scope_bypassed() -> bool:
    return _scope_bypassed.get()


def require_active_organization_id() -> int:
    organization_id = _active_organization_id.get()
    if organization_id is None:
        raise TenantScopeError(
            "No active organization. Wrap the call in tenant_context(organization=...) "
            "or unscoped() if operating across tenants is genuinely intended."
        )
    return organization_id


@contextlib.contextmanager
def tenant_context(
    organization: Organization | int | None = None,
    workspace: Workspace | int | None = None,
) -> Iterator[None]:
    """Run a block with an explicit active tenant.

    Used by the middleware per request, and by Celery tasks, which have no
    request to inherit from and must state the tenant they act for.
    """
    organization_id = getattr(organization, "pk", organization)
    workspace_id = getattr(workspace, "pk", workspace)

    org_token = _active_organization_id.set(organization_id)
    ws_token = _active_workspace_id.set(workspace_id)
    # A nested explicit scope cancels an enclosing bypass, so that
    # unscoped() -> tenant_context() reads the way it behaves.
    bypass_token = _scope_bypassed.set(False)
    try:
        yield
    finally:
        _active_organization_id.reset(org_token)
        _active_workspace_id.reset(ws_token)
        _scope_bypassed.reset(bypass_token)


@contextlib.contextmanager
def unscoped() -> Iterator[None]:
    """Run a block with tenant filtering disabled.

    Legitimate uses are narrow: migrations, the Django admin, platform-wide
    admin reporting (PRD section 75), and cross-tenant maintenance jobs. Call
    sites should be rare enough to review individually.
    """
    token = _scope_bypassed.set(True)
    try:
        yield
    finally:
        _scope_bypassed.reset(token)
