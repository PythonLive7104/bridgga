# ADR 0007 — Container topology, and no MinIO

**Status:** Accepted · **Date:** 2026-10-08

## Context

Docker became available on the development machine, which changes the premise
of [ADR 0006](0006-sqlite-dev-fallback.md): Postgres, Redis and object storage
can now run locally. Phase 2 makes this pressing, because Postgres full-text
search and trigram indexes have no SQLite equivalent.

The previous compose file covered the backend, worker and beat but not the
frontend, so "run the project" was still two manual steps plus a container
stack.

## Decision

**One command runs everything.** `docker compose -f infra/docker-compose.yml
up` starts Postgres (service name `db`), Redis, the API, a Celery worker, beat,
Flower, MailHog, object storage with its bucket created, and the Next.js dev
server. Running natively with `manage.py runserver` and `npm run dev` stays
fully supported — the SQLite fallback is unchanged — because a container
rebuild in the middle of a debugging session is a poor trade.

**One Dockerfile per service, two targets each.** `dev` and `prod` share a
base, an interpreter and a system-package set, so they cannot drift in the ways
that produce "works locally, fails in production". `dev` takes its source from
a bind mount; `prod` copies it, installs no dev dependencies, and bakes in
collected static files.

**Migrations run in the entrypoint, in one service.** The `backend` container
sets `RUN_MIGRATIONS=1`; the worker, beat and Flower share the image and do
not. Three containers starting together would otherwise run `migrate`
concurrently and whichever lost would exit non-zero.

**SeaweedFS instead of MinIO** for local S3-compatible storage. MinIO archived
its repository and deleted its community images from Docker Hub in September
2026; the quay.io mirror now requires authentication. The last free release
carries CVE-2026-40344, a CVSS 8.8 authentication bypass fixed only in the
commercial product. Pinning a mirrored tag would mean running a
known-vulnerable storage service on every developer's machine to save a config
change.

## Consequences

- The storage endpoint was already a setting rather than a hardcoded address,
  so the swap touched compose and nothing in the application. That property is
  worth keeping: production uses a managed object store, not either of these.
- Two package managers now have to agree across three places. The Node image is
  pinned to the host's major version, because a lockfile written by npm 11 is
  validated differently by the npm 10 in `node:22`, and `npm ci` rejects it.
  The same reasoning applies to Python: the image is 3.13 rather than the
  host's 3.14 so that psycopg and argon2-cffi install from wheels.
- `output: "standalone"` in `next.config.ts` is what keeps the production web
  image from shipping the whole dependency tree.
- The rewrite destination in `next.config.ts` moved from `NEXT_PUBLIC_API_URL`
  to `API_PROXY_URL`. It is resolved by the Next server, not the browser, and
  in a container it is an internal hostname that must not be inlined into a
  client bundle.
