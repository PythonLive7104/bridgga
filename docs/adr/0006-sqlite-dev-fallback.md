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
