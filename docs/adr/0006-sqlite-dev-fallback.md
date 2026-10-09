# ADR 0006 — SQLite is a local convenience; CI runs Postgres

**Status:** Accepted · **Date:** 2026-10-08

## Context

Docker is not available on the current development machine, so there is no
local Postgres. The project still needs to be runnable and testable today.

## Decision

`DATABASE_URL` drives the database. Unset, dev and test settings fall back to a
SQLite file. `infra/docker-compose.yml` and CI both set it to Postgres 16, and
**CI always runs the suite on Postgres**.

## Consequences

- A green local run is not sufficient evidence. SQLite differs on constraint
  enforcement, transaction behaviour and JSON handling, so partial unique
  constraints such as `workspace_single_default_per_org` are only genuinely
  proven by the CI run.
- Phase 2 introduces Postgres full-text search and trigram indexes, which have
  no SQLite equivalent. The fallback stops being viable then and
  `django.contrib.postgres` gets added to `INSTALLED_APPS` at that point.

## Addendum, Phase 2.9

That point arrived, and the fallback survived it in a reduced form rather than
being withdrawn.

`apps.companies.search` dispatches on the connection vendor: ranked full-text
with weighting and trigram similarity on Postgres, a plain substring match on
SQLite. Filters, ordering and pagination are identical either way, so only
relevance differs. The GIN and trigram indexes are created by a migration that
skips on anything but Postgres (`apps.common.db_operations.PostgresOnlyIndex`),
and the model state is applied on both so `makemigrations --check` stays
quiet.

The split is only defensible while it is visible, so three things make it so:

- `search_backend()` reports which one answered, and the API returns it on
  every prospect response;
- the prospect table says, in the interface, when a result came from substring
  matching;
- the tests that assert ranking behaviour are skipped off Postgres rather than
  weakened to pass. A test that passes by asserting less is worse than one
  that does not run, and CI runs Postgres, so they run where it counts.

What is still true from the original decision: a green local run is not
sufficient evidence.
