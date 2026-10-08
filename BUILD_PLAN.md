# Palatial — Build Process Plan

Derived from `prd.md` (AI Customer Acquisition OS, v1.0). Section references like **§32** point at PRD sections.

**Frontend direction:** explee.com-class craft (minimal chrome, outcome-led hero, animated pipeline demo, metric-bearing proof, transparent unit pricing) applied to this PRD's own positioning. See Part C.

---

## Part A — Decisions to lock before any code

Do not start Phase 1 until these are answered in writing. Each is expensive to reverse.

| # | Decision | Recommendation | Why |
|---|---|---|---|
| A1 | One frontend or two? | **One Next.js 15 app** with route groups `(marketing)` and `(app)` | PRD wants SSG/SSR for SEO (§19) *and* a React dashboard (§114). One app = one design system, one deploy, no duplicated auth. |
| A2 | Frontend stack | Next.js 15 App Router, TypeScript, Tailwind v4, shadcn/ui primitives, TanStack Query, Zustand for light client state, next-intl, Recharts, Framer Motion | Covers every §114 component. next-intl satisfies "translation keys, not hardcoded text" (§113) from day one. |
| A3 | Backend stack | Django 5.x + DRF, PostgreSQL 16, Redis 7, Celery + beat, S3-compatible storage via django-storages, drf-spectacular to a generated TS client | Matches the PRD header. A generated client kills frontend/backend drift. |
| A4 | Auth implementation | **django-allauth headless** + HttpOnly same-site session cookies | One library covers email/password, verification, reset, Google, Microsoft, magic link, TOTP MFA — all of §23. Cookies beat localStorage JWTs for XSS. |
| A5 | Tenancy model | Shared schema; `organization_id` + `workspace_id` FK on every tenant row, enforced by a base model, a manager, and a DRF mixin. Postgres RLS later if enterprise demands it | §65 asks for tenant-aware querysets and tests, not separate schemas. |
| A6 | Content source of truth | Django `content` app (fields per §86) served to Next.js via ISR | Lets non-engineers edit later; avoids a second CMS bill. MDX only for engineering docs. |
| A7 | Monorepo layout | See below | |
| A8 | Brand name + domain | Decide now — §133 leaves it open | Blocks DNS, SPF/DKIM, OAuth app registration, and payment KYC. |

```text
palatial/
├─ backend/
│  ├─ config/                 # split settings, celery.py, urls, asgi
│  ├─ apps/                   # per §79
│  │  ├─ accounts/ organizations/ billing/
│  │  ├─ companies/ contacts/ leads/ intelligence/ signals/
│  │  ├─ campaigns/ messaging/ conversations/
│  │  ├─ crm/ opportunities/ analytics/
│  │  ├─ ai/ integrations/ notifications/ compliance/ content/
│  │  └─ api/                 # v1 routers only; logic lives in services.py
│  └─ pyproject.toml
├─ web/                       # Next.js: (marketing) + (app) route groups
├─ packages/ui/               # design tokens + shared components
├─ infra/                     # docker-compose, Dockerfiles, deploy
└─ docs/
```

### Long-lead items — start on day 1, they gate later phases

Multi-day to multi-week external approvals. Starting them in the phase that needs them will stall the build.

1. **Amazon SES production access** (sandbox to prod review), and/or SendGrid/Postmark.
2. **Meta WhatsApp Business Platform** app, business verification, message-template approval (§40). Weeks, not days.
3. **Paystack and Flutterwave** merchant accounts + KYC; Stripe for international (§67).
4. **Google Cloud and Microsoft Entra OAuth apps**, including Gmail/Calendar and Graph scopes — restricted scopes need a verification process.
5. **Licensed data-provider contracts** (§84) — review usage rights before writing a single enrichment call.
6. **Legal review** of large-scale personal-data enrichment (§62 states this is required before production), plus privacy policy, AUP, and DPA drafts.

---

## Part B — The build process

Seven phases. Each has an **exit gate**; do not advance until it passes.

### Phase 0 — Validation (manual, 2–3 weeks, no platform code)

PRD §127 is explicit: prove the workflow by hand first.

1. Pick the vertical: African B2B tech — SaaS, cybersecurity, fintech infra, logistics software, dev tools, agencies (§128).
2. Use TryNoBot as design-partner zero (§95). Recruit 5–10 external design partners.
3. By hand: write one ICP, source 50 prospects, research each, write a reason-to-contact, send personalized outreach, log every reply, meeting, and outcome.
4. Record which fields you actually used to make each decision. **Those columns are your real data model** — they will differ from the PRD's guess, and the PRD's guess should lose.
5. Note every task repeated more than five times. Those are the only things worth automating first.

**Exit gate:** one written ICP, 50 prospects each with an evidence-backed reason-to-contact, at least 3 meaningful replies, and a list of repeated manual tasks ranked by time spent.

---

### Phase 1 — Foundation

| Step | Work |
|---|---|
| 1.1 | `git init`; monorepo scaffold; pnpm workspace; `uv` or Poetry; pre-commit (ruff, black, mypy, eslint, prettier) |
| 1.2 | `infra/docker-compose.yml`: postgres, redis, backend, worker, beat, mailhog, minio |
| 1.3 | Django config: split settings, env parsing, structlog JSON logging, Sentry, health endpoints |
| 1.4 | `accounts`: custom User, UUID public IDs (§80). `organizations`: Organization, Workspace, Membership, the five roles (§66) |
| 1.5 | **Tenancy primitives**: `TenantOwnedModel`, tenant-scoped manager, request-scoped org resolver, `TenantScopedViewSet`, object-level permission classes |
| 1.6 | `test_tenant_isolation.py` — a parameterized test walking every registered tenant model, asserting org B cannot read, write, or enumerate org A's rows. Write it now; it stays green forever |
| 1.7 | Auth: allauth headless — password, verification, reset, Google, Microsoft, magic link, TOTP MFA (§23) |
| 1.8 | `audit`: AuditLog + decorator; wire the §111 action list as handlers are built |
| 1.9 | API skeleton: `/api/v1/`, drf-spectacular schema, cursor pagination, filter backends, throttling, uniform error envelope, idempotency keys (§53) |
| 1.10 | Celery: queues `default / crawl / enrich / ai / send / analytics`, retry and backoff policy, dead-letter handling, beat schedule, Flower |
| 1.11 | Frontend: Next.js app, design tokens, the §114 primitive set, auth screens, app shell and sidebar exactly per §115, generated TS client wired to TanStack Query |
| 1.12 | Billing *foundation only*: Plan, Subscription, CreditBalance, UsageRecord models plus a provider interface. No checkout yet |
| 1.13 | CI/CD: GitHub Actions (lint, typecheck, test, `makemigrations --check`, build), staging deploy, branch protection |

**Exit gate:** a new user signs up with MFA, creates an organization and workspace, invites a teammate with a role, and lands on an empty dashboard. Tenant-isolation suite green. OpenAPI client generates clean.

---

### Phase 2 — Intelligence

This is the product's actual differentiator (§101). Build it carefully.

1. **Hardened crawler** (§109) — build this *before* anything that fetches a URL. Validate scheme; resolve DNS and reject private, loopback, link-local, and cloud-metadata ranges *after* resolution; cap redirects; enforce timeout and response-size limits; strip scripts; run on an isolated `crawl` queue with its own egress rules. Add the SSRF tests from §108.
2. **AI layer** (§56–59): `AIProvider` abstraction (OpenAI / Anthropic / Gemini / local), prompt registry with version pinning, Pydantic output schemas with validate-and-retry, an `AIJob` + `AIUsage` ledger (org, user, feature, model, tokens, cost), a model-routing table (cheap models for classification and extraction, strong models for research and strategy), and an **evidence object** (`source`, `source_url`, `retrieved_at`, `confidence`) that every claim must carry (§58).
3. **Eval harness before agents**: fixture datasets, schema-validity tests, hallucination tests, prompt-regression tests (§106). An agent without an eval set is unshippable.
4. `CompanyUnderstandingAgent` to an editable `CompanyProfile` (§26). Every AI field editable.
5. `ICPAgent` to an `ICP` (company profile, buyer profile, pain signals) with a full manual-edit UI (§27).
6. `MarketRecommendationAgent` plus seeded `CountryProfile` records for the ten launch countries and the §72 currencies, each recommendation carrying its reasoning (§28, §71).
7. Data model: Company, Person, CompanyTechnology, CompanyEvent, Lead, LeadSource — with provenance on every record (§61) and contact-quality statuses (§60).
8. Import pipeline: CSV/XLSX/API to dedupe to validate to enrich to score (§51).
9. **Prospect discovery**: Postgres FTS, trigram, and composite indexes across the §29 filter set; saved searches; prospect table with the §117 columns and actions. Target under 2s (§103).
10. **Signal engine** (§33): `LeadSignal` with type, source, timestamp, confidence, evidence, staleness. First detectors: hiring pages, funding news, website diffing, tech-stack change, new pages and pricing changes.
11. **Opportunity score** (§32): configurable weights, a stored component breakdown, and an explainability payload rendered per §119.
12. `ResearchAgent` (§34): summary, why-they-may-buy, suggested approach, personalization points, confidence, evidence.
13. **"Why contact this company?"** (§35) — the highest-leverage string in the product. Evidence-linked, never a free-text LLM flourish.
14. **Website Sales Audit** (§49) — ship it here; it doubles as the flagship free tool in Phase 6.
15. Onboarding wizard steps 1–5 (§25).

**Exit gate:** enter a website, get an editable company profile, generate an ICP, pick a country, search, and receive scored prospects each carrying signals, evidence, and a reason-to-contact a human agrees with. Then compare against Phase 0's hand-built list: **does the machine find prospects as good as the ones you found by hand?** If not, stop and fix targeting before building outreach.

---

### Phase 3 — Acquisition

1. **Compliance core first** (§62–63): SuppressionEntry, a mandatory suppression check in the send path that cannot be bypassed, unsubscribe tokens and landing page, consent records, regional policy config. Before the first message can be sent, not after.
2. Mailbox connections: Gmail OAuth, Microsoft Graph, generic SMTP/IMAP, SES/SendGrid/Mailgun/Postmark (§39). Domain verification plus an SPF/DKIM/DMARC checker with guidance.
3. Campaign, Sequence, and Message models (§36); scheduler with per-mailbox rate limits, warmup ramp, sending windows, recipient-timezone awareness.
4. `PersonalizationAgent` plus approval modes and sample-message preview.
5. **Pre-launch panel** (§36): estimated audience, estimated AI cost, message volume, compliance warnings, sample messages. Launch is explicitly human-approved (§8.4).
6. AI Campaign Planner — natural language in, draft campaign out, approval required (§37).
7. Delivery plus provider webhook ingestion: bounces, complaints, opens; sender-reputation monitoring.
8. Reply sync (Gmail / Graph / IMAP / inbound webhooks), thread matching, `Conversation` model.
9. **Unified Inbox** (§43) with AI summary, recommended response, CRM stage, next action.
10. Abuse prevention (§64): complaint-rate and volume thresholds to warn, throttle, pause campaign, review, suspend.

**Exit gate:** launch a small real campaign from a connected mailbox, see delivery and bounce events, receive a real reply in the Unified Inbox, and confirm an unsubscribe suppresses that person globally and blocks re-enrollment.

---

### Phase 4 — Sales and revenue (completes the MVP, §92)

1. `ReplyClassificationAgent` — the 12 labels in §42, with a labeled eval set and a confusion matrix in CI.
2. CRM (§44): the default nine-stage pipeline, custom pipelines, kanban and table views, tasks, ownership.
3. Meetings (§45): Google Calendar, Microsoft Calendar, Calendly, Cal.com; booking links, availability, reminders, opportunity association.
4. The Opportunity to Deal to Customer to RevenueEvent chain (§80).
5. **Revenue attribution** (§46) — the campaign-to-revenue join that answers "which campaigns are generating money?"
6. Analytics aggregation jobs and dashboards (§47), dashboard layout per §116, campaign analytics per §118 with qualified opportunities and revenue given visual priority.
7. `GrowthAdvisorAgent` (§48): diagnosis, evidence, recommendations, expected impact.
8. Billing for real (§67–69): Paystack, Flutterwave, Stripe; plans, seats, usage, credits with pre-operation cost estimates, invoices, tax fields, upgrade/downgrade/cancel, dunning.
9. Notifications (§73) across email and in-app.
10. Data rights: async export (§122), account deletion flow (§121), configurable retention (§120).
11. **The critical E2E test (§107)** — signup through "revenue appears in analytics" — running in CI on every merge.
12. Walk the 28-item Definition of Done (§135) as a literal checklist.

**Exit gate:** all 28 §135 items pass on staging, performed by someone who did not build the feature. The §107 E2E test is green in CI.

---

### Phase 5 — African advantage

1. WhatsApp Business Platform (§40): approved templates, inbound conversations, permitted outbound messages, opt-out handling, AI-assisted replies. Official API only — the PRD forbids unauthorized automation.
2. Country intelligence depth (§71): city-level clusters, industry density, business hubs, regulatory references.
3. Multi-currency throughout (§72) and local payment polish.
4. Channel-preference engine per country (§70), user-configurable.
5. French locale via next-intl plus locale-aware AI generation (§113); `/fr/`, `/fr-ci/`, `/fr-sn/` routing (§22).
6. Localized vertical playbooks.

---

### Phase 6 — Growth (marketing site, SEO, AEO)

1. `content` app with the §86 field set; ISR-rendered Next.js routes; editor preview mode.
2. The public IA per §11 — build pages that have real content, not the whole route list at once.
3. SEO infrastructure (§19): dynamic sitemaps, robots, canonicals, OpenGraph, breadcrumbs, redirect management, hreflang, 404s, noindex controls, and a Core Web Vitals budget enforced in CI via Lighthouse CI.
4. Structured data (§21) only where eligible.
5. AEO page template (§20): question heading, concise direct answer, supporting detail, examples and tables, author, published and updated dates, related questions.
6. The ten free tools (§17), each with a genuinely useful ungated result.
7. Country (§13), industry (§14), and use-case (§15) pages — **gated on real localized value**; the PRD twice forbids thin auto-generated localization.
8. Comparison pages (§16), including an honest `/compare/explee` that states where they are stronger.
9. Original research reports from lawful aggregated data (§18); case studies with verified metrics only (§88).
10. Trust Center (§76), Status page (§77), documentation (§78).

---

### Phase 7 — Scale

1. CRM integrations (§50): HubSpot, Salesforce, Pipedrive, Zoho, Close — OAuth, field mapping, conflict handling, retries, logs.
2. Public API and Developer Portal (§53–55): hashed API keys, rate limits, versioning, webhooks with signing secrets, idempotency, delivery logs; Python and JS SDKs.
3. AI Sales Agent Copilot then Autopilot (§41), gated on an approved knowledge base, communication policy, prohibited topics, escalation rules, rate limits, audit logs.
4. OpenSearch migration when Postgres search stops meeting the 2s target (§83).
5. Enterprise readiness (§123): SSO, SAML, SCIM, audit exports, custom retention, DPA, SLA.
6. Predictive intent and semantic company search (§93, Phase 3).

---

### Cross-cutting, every phase

- **Security testing** (§108): cross-tenant access, IDOR, privilege escalation, webhook spoofing, key leakage, prompt injection, malicious prospect content, SSRF, rate-limit bypass.
- **Observability** (§105): API errors, Celery failures, AI and provider failures, message and webhook failures, queue depth, database and Redis health.
- **Accessibility** (§112): WCAG 2.2 AA, keyboard navigation, focus indicators, reduced motion — in the component layer, not retrofitted.
- **Audit logging** (§111) wired as each sensitive action ships.
- **i18n keys** from the first component, even while English-only.
- **Product analytics** (§89): instrument the activation funnel early or you will have no baseline.

---

## Part C — Frontend design spec

### What to take from explee.com

Observed pattern on their homepage:

- Near-empty header: logo left, three nav items right (Products, Pricing, Sign in), one primary CTA. No mega-menu.
- A single outcome-led hero headline with a one-sentence subhead naming the agent pipeline, a prominent CTA, and free-credit reassurance microcopy directly beneath it.
- **A step-by-step pipeline walkthrough as the page's centrepiece** — website input, analysis, targeting, outreach, reply handling, optimization — rendered with realistic data (contact names, emails, cost-per-lead) rather than marketing abstractions.
- Testimonial cards that each carry a hard number (lead volume, cost per lead) with quotes kept short.
- Transparent unit pricing stated as a per-email figure with an outcome range, no subscription complexity on the page.
- An accordion FAQ covering setup, cost, deliverability, and compliance.
- A multi-column footer organized by product, databases by region, and resources, with company registration details.
- Light and dark modes, neutral palette, one accent, generous whitespace, progressive disclosure down the page.

### What *not* to take

Explee leads with "hot leads in 24 hours." Your PRD explicitly rejects that positioning (§99: not a lead generator, not cold-email software, not a lead database) and names evidence-backed scoring and revenue attribution as the differentiators (§101, §136). **Copy their craft, not their message.** Also write your own copy, layout rhythm, and illustrations — matching the quality bar, not the page.

### Design tokens

- **Theme:** dark-first with a true light mode. Define all colors as CSS custom properties on `:root`, redefine under `@media (prefers-color-scheme: dark)` guarded by `:root:not([data-theme="light"])` and again under `:root[data-theme="dark"]`.
- **Palette:** a neutral gray ramp (12 steps) plus one saturated accent for CTAs and data emphasis. Add semantic tokens for signal strength (hot / warm / cold) and score bands, since the product leans heavily on scored and ranked data.
- **Type:** one geometric or neo-grotesque sans (Inter, Geist, or Satoshi). Hero at `clamp(2.5rem, 6vw, 4.5rem)`, tight tracking, weight 600–700. Body at 16–17px with 1.6 line height.
- **Surfaces:** 1px hairline borders, 12–16px radii, soft layered shadows, restrained gradient washes behind the hero and section transitions. No glassmorphism on text-bearing surfaces — it hurts contrast.
- **Spacing:** an 8px scale; 96–160px of vertical rhythm between marketing sections.

### Marketing page composition (maps to §12)

| Order | Section | Build note |
|---|---|---|
| 1 | Hero | Headline "Turn your website into a customer acquisition engine" (§12), subhead, "Find My Customers" primary CTA, "See How It Works" secondary, reassurance microcopy |
| 2 | Problem | Short, contrasting activity metrics against revenue (§8.1) |
| 3 | **Pipeline walkthrough** | The signature piece. An auto-advancing stepper: website in, ICP, markets, prospects, signals, research, outreach, reply, meeting, revenue. Build each step from **real design-system components with seeded demo data**, not screenshots — it stays truthful, localizable, and does not rot |
| 4 | Prospect intelligence | A live-feeling prospect table using the §117 columns |
| 5 | Buying signals | Signal cards with source, timestamp, and confidence (§33) — show the evidence, that is the product |
| 6 | AI research + "Why contact this company?" | Render the §35 example format verbatim in shape: claim, confidence, evidence list (§119) |
| 7 | Personalized outreach | Before/after message panels |
| 8 | AI sales agent | The three modes as tabs: Manual, Copilot, Autopilot (§41) |
| 9 | CRM and pipeline | Kanban preview |
| 10 | **Revenue attribution** | Give this the most visual weight — it is the §136 third question and the strongest differentiator |
| 11 | Africa-first | Country chips for the ten launch markets, channel-mix per country (§70) |
| 12 | International | The reverse flow: selling into Africa (§6.2) |
| 13 | Integrations | Logo grid |
| 14 | Case studies | Verified metrics only (§88) |
| 15 | Security | Link to the Trust Center |
| 16 | Pricing | Plan cards plus an interactive estimator that doubles as a §17 free tool |
| 17 | FAQ | AEO-structured accordion (§20) |
| 18 | Final CTA | |
| 19 | Footer | Multi-column: Product, Features, Solutions (industry / use case / country), Databases by country, Resources, Company, Legal, plus a locale switcher |

### Motion

Scroll-reveal on section entry, number count-ups on metrics, auto-advancing pipeline steps with manual override, and hover elevation on cards. Every one of these must be disabled under `prefers-reduced-motion` (§112). Keep the hero free of layout-shifting animation to protect CLS (§103).

### App shell (authenticated)

Fixed left sidebar with the §115 group structure exactly as written (Overview; Find Customers; Engage; Sell; Analyze; Integrations; Billing; Settings). Collapsible to icons. Top bar holds the workspace switcher, global search, a command palette (Cmd-K, §114), notifications, and the user menu. Dashboard laid out per §116. Build the §114 component set in `packages/ui` **before** feature work, or the modules will drift apart.

---

## Part D — Suggested sequencing

Assumes a small team. Adjust to your actual headcount.

| Phase | Rough duration | Can run in parallel with |
|---|---|---|
| 0 Validation | 2–3 weeks | Long-lead applications, A1–A8 decisions |
| 1 Foundation | 3–4 weeks | Design-system build, Phase 0 tail |
| 2 Intelligence | 6–8 weeks | Marketing hero + pipeline section |
| 3 Acquisition | 4–6 weeks | Free tools |
| 4 Sales and revenue | 5–7 weeks | — |
| **MVP ships here** | | §135 checklist, §107 E2E |
| 5 African advantage | 4–6 weeks | Phase 6 content |
| 6 Growth | ongoing | everything |
| 7 Scale | ongoing | driven by customer demand |

### First ten working days

1. Answer A1–A8; commit the decisions as `docs/adr/`.
2. File every long-lead application in the list above.
3. `git init`, monorepo scaffold, docker-compose up, CI green on an empty test.
4. Custom User, Organization, Workspace, Membership, roles — plus the tenant-isolation test.
5. Start Phase 0's manual prospecting the same week. It runs alongside the scaffolding and it is what tells you whether any of the rest is worth building.
