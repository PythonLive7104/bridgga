# Bridgga — AI Customer Acquisition OS

Find the companies most likely to need what you sell, reach the right decision
makers, start relevant conversations, and connect acquisition activity to
revenue.

- [prd.md](prd.md) — product requirements
- [BUILD_PLAN.md](BUILD_PLAN.md) — phased build process
- [docs/adr/](docs/adr/) — architecture decisions and why

**Status: Phase 2 (Intelligence) in progress.** Phase 1 is complete — auth,
organizations, workspaces, roles, tenancy, audit log, billing models, API
skeleton, Celery queues, the design system and the marketing site. Phase 2 has
the SSRF-hardened website fetcher, the AI layer (providers, versioned prompt
registry, cost ledger), the eval harness, the company-understanding agent
behind an editable company profile, and the ICP builder. Next: the market
recommendation engine. No prospects or campaigns yet.

---

## Layout

```text
backend/     Django 6.0 + DRF. Apps under backend/apps/, config in backend/config/
web/         Next.js 15 App Router: (marketing), (app) and auth route groups
infra/       docker-compose, Dockerfiles, entrypoint
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

### Everything at once, in Docker

One command, from the repository root:

```bash
docker compose -f infra/docker-compose.yml up --build
```

That builds and starts all ten services. First run takes a few minutes; after
that drop `--build` unless a dependency changed.

| | |
|---|---|
| http://localhost:3000 | the app and marketing site |
| http://localhost:8000 | the API directly (the app reaches it through the proxy) |
| http://localhost:8025 | MailHog — every verification and invitation mail lands here |
| http://localhost:5555 | Flower — Celery queues and task history |
| http://localhost:8888 | SeaweedFS filer — browse what the app uploaded |
| localhost:5432 | Postgres, as `bridgga` / `bridgga` |

Migrations run automatically on boot, in the `backend` container only — see
`infra/entrypoint.backend.sh` for why the worker and beat must not.

Day-to-day:

```bash
# Follow logs (all services, or one)
docker compose -f infra/docker-compose.yml logs -f
docker compose -f infra/docker-compose.yml logs -f backend worker

# Any manage.py command
docker compose -f infra/docker-compose.yml exec backend python manage.py createsuperuser
docker compose -f infra/docker-compose.yml exec backend python manage.py seed_plans

# Tests, against Postgres rather than the SQLite fallback
docker compose -f infra/docker-compose.yml exec backend python -m pytest -q

# Stop; add -v to also discard the database and uploads
docker compose -f infra/docker-compose.yml down
```

Source is bind-mounted, so an edit on the host reloads in the container: Django
through its autoreloader, Next through `next dev`. Only a dependency change
needs a rebuild.

Development credentials are committed in `infra/docker-compose.yml` on purpose.
Override anything real in `infra/.env` (gitignored, read automatically) —
`infra/.env.example` lists what is worth setting, including a Resend API key if
you want real mail instead of MailHog.

### Or natively, one terminal each

If you would rather not run the app in Docker, the two commands you expect work
from their own directories — this is the layout the project is in:

```bash
# terminal 1
cd backend && .venv/Scripts/python manage.py runserver

# terminal 2
cd web && npm run dev
```

With no `DATABASE_URL` or `REDIS_URL` set, that uses the SQLite and in-process
Celery fallbacks and needs no containers at all. To keep native servers but get
real Postgres and Redis, start only the infrastructure:

```bash
docker compose -f infra/docker-compose.yml up -d db redis mailhog storage storage-init
```

then put this in `backend/.env`:

```bash
DATABASE_URL=postgresql://bridgga:bridgga@localhost:5432/bridgga
REDIS_URL=redis://localhost:6379/0
```

Note the host differs by where the client runs: `db` is the hostname inside the
compose network, `localhost` from a process on your machine.

## Configuration, and what goes on a server

Two env files, with different jobs:

| File | Read by | Holds |
|---|---|---|
| `backend/.env` | the Django settings module, so **every** process: web, Celery worker, beat, management commands | application config — secret key, `DATABASE_URL`, `REDIS_URL`, AI keys, mail, account policy |
| `infra/.env` | `docker compose` only | the local stack — host ports, the Postgres container's own credentials |

`backend/.env` is the file to put on a server. Nothing else carries
application config, and a variable already set in the real environment always
wins over it, so a process manager or secrets store can override any line
without editing the file.

Two things to know:

- **Hostnames differ by vantage point.** `localhost:5432` from a process on
  your machine, `db:5432` from inside the compose network, the real host on a
  server. The same applies to Redis. `backend/.env.example` spells out which
  line you want.
- **Do not add application settings to `docker-compose.yml`.** A variable
  named there is injected into the container even when empty, and an empty
  value still counts as set — so it silently shadows the real one in
  `backend/.env`. Only values that must point at a compose service
  (`DATABASE_URL`, `REDIS_URL`, `EMAIL_HOST`) belong there.

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
