# ADR 0003 — Tenant isolation in three layers

**Status:** Accepted · **Date:** 2026-10-08

## Context

PRD section 65 requires tenant-aware querysets, object-level authorisation and
tests for cross-tenant access. Any single enforcement point will eventually be
forgotten by a future contributor.

## Decision

Shared schema, with `organization_id` on every tenant row, enforced three times
over:

1. **`TenantManager`** narrows `objects` to the active organization held in a
   `ContextVar`, so a bare `Model.objects.all()` in a request is already scoped.
2. **`TenantScopedViewSet`** filters by `request.organization` explicitly and
   does not rely on layer 1, so a bug in either alone cannot leak data.
3. **`tests/test_tenant_isolation.py`** discovers every concrete subclass of
   `TenantOwnedModel` from the app registry and asserts isolation for each.

Crossing tenants requires the explicit `unscoped()` context manager, which makes
a leak a reviewable line of code rather than an omission.

## Consequences

- A new tenant model is covered by the isolation suite the moment it subclasses
  `TenantOwnedModel`. Declaring a raw `organization` field instead bypasses both
  the scoping and the test, so the base class is mandatory.
- Opting a model out requires `tenant_isolation_exempt_reason` on the model,
  which surfaces in the diff.
- Postgres row-level security remains available later if enterprise requires
  defence below the ORM.
