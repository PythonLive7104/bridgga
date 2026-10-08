# ADR 0002 — One Next.js app, not two frontends

**Status:** Accepted · **Date:** 2026-10-08

## Context

The PRD wants SSG/SSR for SEO-critical marketing pages (section 19) and a
React dashboard (section 114). That could be two deployables or one.

## Decision

One Next.js 15 App Router application with route groups: `(marketing)` for the
public site, `(app)` for the authenticated product, and `auth/` for sign-in.

## Consequences

- One design system, one build, one deploy. No duplicated auth handling.
- The API is proxied same-origin through `next.config.ts` rewrites, so the
  session cookie stays `SameSite=Lax` instead of requiring `SameSite=None`.
- Marketing pages must stay server-rendered; a stray client-only dependency in
  `(marketing)` would silently cost SEO. The build output report is the check.
