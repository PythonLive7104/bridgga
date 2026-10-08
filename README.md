# Palatial — AI Customer Acquisition OS

Find the companies most likely to need what you sell, reach the right decision
makers, start relevant conversations, and connect acquisition activity to
revenue.

- [prd.md](prd.md) — product requirements
- [BUILD_PLAN.md](BUILD_PLAN.md) — phased build process
- [docs/adr/](docs/adr/) — architecture decisions and why

**Status: Phase 1 (Foundation) complete.** Auth, organizations, workspaces,
roles, tenancy, audit log, billing models, API skeleton, Celery queues, the
design system and the marketing site are in. No prospects, campaigns or AI yet
— that is Phase 2 onward.

---

## Layout

```text
backend/     Django 6.0 + DRF. Apps under backend/apps/, config in backend/config/
web/         Next.js 15 App Router: (marketing), (app) and auth route groups
infra/       docker-compose and Dockerfile
docs/adr/    Architecture decision records
```

## Running it

### Backend

```bash
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements/dev.txt   # Windows
cp .env.example .env

.venv/Scripts/python manage.py migrate
.venv/Scripts/python manage.py seed_plans
.venv/Scripts/python manage.py createsuperuser
.venv/Scripts/python manage.py runserver
```

On macOS or Linux use `.venv/bin/python`.

Without `DATABASE_URL` and `REDIS_URL` set, the backend uses a local SQLite
file, an in-memory cache, and runs Celery tasks inline. That is a convenience
for working without Docker — see
[ADR 0006](docs/adr/0006-sqlite-dev-fallback.md). CI always runs on Postgres.

### Frontend

```bash
cd web
npm install
cp .env.example .env.local
npm run dev
```

The app expects the backend on `http://localhost:8000` and proxies to it
same-origin, so the session cookie and CSRF work without cross-site cookie
settings.

### Full stack with Postgres and Redis

```bash
docker compose -f infra/docker-compose.yml up
```

Brings up Postgres, Redis, the API, a Celery worker, beat, MailHog
(`:8025`, catches outbound mail) and MinIO (`:9001`).

## Checks

```bash
# Backend
cd backend
.venv/Scripts/python -m pytest              # full suite
.venv/Scripts/python -m pytest -m tenancy   # cross-tenant isolation only
.venv/Scripts/python -m ruff check .
.venv/Scripts/python -m ruff format --check .
.venv/Scripts/python manage.py makemigrations --check --dry-run

# Frontend
cd web
npm run typecheck && npm run lint && npm run format:check
npm run build   # stop `npm run dev` first -- see below
```

> `next build` and `next dev` share the `web/.next` directory, so building
> while the dev server is running overwrites the chunks it is serving and the
> dev server starts returning 500s. Stop the dev server before building, or
> `rm -rf web/.next` and restart it if you forget.

## API

- `GET /healthz` — liveness, touches nothing
- `GET /readyz` — readiness, checks database and cache
- `/api/v1/` — versioned REST API
- `/api/schema/` and `/api/docs/` — OpenAPI schema and Swagger UI
- `/auth/browser/v1/` — allauth headless: password, email verification, reset,
  Google, Microsoft, login-by-code, TOTP MFA

Regenerate the typed frontend client after changing a serializer:

```bash
cd backend && .venv/Scripts/python manage.py spectacular --file schema.yml
cd ../web && npm run api:generate
```

## Two things to know before changing code

**Tenancy.** Every customer-owned model must subclass `TenantOwnedModel` (or
`WorkspaceOwnedModel`). That is what enrols it in automatic query scoping *and*
in the generic isolation test, which discovers models from the app registry.
Declaring your own `organization` field instead bypasses both silently. Reading
across tenants requires the explicit `unscoped()` context manager. See
[ADR 0003](docs/adr/0003-tenancy.md).

**Authorisation.** Views declare a capability; they do not check roles inline:

```python
class CampaignViewSet(TenantScopedViewSet):
    required_capability = Capability.CAMPAIGN_VIEW   # guards reads
    write_capability = Capability.CAMPAIGN_MANAGE    # guards mutations
```

A view declaring neither is denied rather than allowed, so forgetting fails
closed. The role-to-capability matrix lives in
`backend/apps/organizations/roles.py`.
