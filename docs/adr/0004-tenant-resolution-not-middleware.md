# ADR 0004 — Resolve the active organization in DRF, not middleware

**Status:** Accepted · **Date:** 2026-10-08

## Context

The active organization was first resolved in Django middleware. That broke
immediately under test: Django middleware runs *before* DRF authenticates, so
it only ever sees the user that `AuthenticationMiddleware` restored from the
session. Any DRF-level scheme — API keys and service tokens in Phase 7, or
`force_authenticate` in tests — authenticates inside the view, after middleware
has already concluded the caller was anonymous.

## Decision

Resolution lives in `apps.common.tenant_resolution.resolve_tenant`, called from
the `RequireOrganization` permission class. Middleware keeps only request-id
correlation.

`RequireOrganization` is listed first in `permission_classes` so later
permissions and the view body can rely on `request.organization`.

## Consequences

- One code path works for every authentication scheme, present and future.
- The `X-Organization` header only *selects*; membership is re-read from the
  database on every request, so forging it gains nothing and a revoked
  membership takes effect immediately.
- Selecting an organization the caller does not belong to returns **404, not
  403**: a 403 would confirm that organization exists and leak other tenants.
- A user in several organizations with no header gets no tenant rather than a
  guessed one, because guessing writes data into the wrong tenant.
