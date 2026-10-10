# ADR 0011 — The audit measures what can be measured

**Status:** Accepted · **Date:** 2026-10-10

## Context

PRD §49 asks the website sales audit for eight scores — value proposition, ICP
clarity, CTA, trust, pricing clarity, conversion, SEO, AEO readiness — plus
performance observations and recommendations.

§17 makes the same thing a free acquisition tool: a stranger pastes a URL and
gets a result without an account. It is therefore the first thing many people
will ever see the product do, in front of somebody who knows their own website
better than we do.

The obvious implementation sends the page to a model and asks for eight
numbers.

## Decision

Five of the eight dimensions are **counted from the HTML** and never asked of a
model: CTA, trust, pricing clarity, SEO, AEO. Each is a set of weighted checks
in `apps.intelligence.audit_checks`, and each check returns what it found plus,
on failure, what to do about it.

Three are **judged by a model**: value proposition, ICP clarity, conversion.
Those are questions about meaning, and no checklist answers them.

The model is shown the measurements and told not to contradict them. The
interface labels each dimension `measured` or `judged`.

Performance is reported as **observations with no score**.

## Why

**A score nobody can reproduce is a score nobody can act on.** "SEO 62" from a
model is unfalsifiable and unactionable. "No meta description, so the search
engine writes its own" is a task. The audit's deliverable is the second thing;
the number exists to order them.

**The reader will check the first thing they can check.** They know whether
their page has testimonials. A model that scores trust at 40 on a page with
three case studies has lost them, and nothing later in the report recovers it.
Giving the model the measurements is what prevents the single most
embarrassing possible output — recommending they add what they already have —
and an eval case asserts it.

**It is free and it runs for anybody.** Most of the audit costs nothing to
produce, which is what makes it affordable to give away without a signup gate.

**Performance cannot be measured honestly from HTML.** Real numbers need a
rendering engine and a network trace. Page weight, script count and server
response time are suggestive and worth showing; turning them into a score
would be exactly the false precision the rest of this decision avoids.

## Consequences

- **The audit survives the model failing.** The measured half has already run
  by the time the model is called, so a failed call produces five dimensions of
  checkable findings rather than an error page. `judged=false` says so, and the
  interface states it.
- **An unscored dimension is dropped, not zeroed** — ADR 0009's rule, reused.
  Zeroing the three judged dimensions would cap every measured-only audit at
  60 with no explanation.
- **A new check is a function, not a prompt change**, and arrives with its own
  test. The failure modes of the measured half are ordinary bugs.
- The checks encode opinions (one `h1`, 50–165 character descriptions,
  "contact us for pricing" is a gate). They are defensible, conventional, and
  stated in the output, so a reader who disagrees can see exactly what was
  asserted and dismiss it.

## Not tenant-owned, deliberately

`WebsiteAudit` is the one customer-facing model that is not a
`TenantOwnedModel`. An anonymous visitor has no organization, and the result's
visibility rule is "whoever has the link" — it is made to be shared. Forcing it
into the tenant model would mean inventing a tenant per visitor and describing
the access rule as something it is not. `organization` records who asked, not
who may read, and a test asserts both that it is outside the isolation sweep
and why.

What replaces authentication: the SSRF-hardened fetcher (§109), an IP-keyed
throttle, a one-hour cache per URL, and AI spend ledgered to a members-less
"public tools" organization — so the cost of the free tool is a query rather
than a surprise on an invoice.
