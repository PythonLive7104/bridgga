# ADR 0009 — An unmeasured score component is not a zero

**Status:** Accepted · **Date:** 2026-10-09

## Context

PRD §32 defines the opportunity score as eight weighted components summing to
100: ICP fit 25, buying intent 20, pain evidence 15, company growth 10,
technology fit 10, geographic fit 5, contact quality 5, engagement 10.

Most of what those components need does not exist for most prospects at the
moment they are first scored:

- **Engagement does not exist at all** until campaigns ship in Phase 3.
- **Buying intent, growth and pain evidence** need signals, which need the
  company's site to have been crawled at least twice.
- **Technology fit** needs a detected stack.
- **Contact quality** needs a person, which arrives later in the pipeline than
  the company does.

The obvious implementation — score each component, multiply by its weight,
add up — produces a number that is confidently wrong.

## Decision

A scorer returns `None` for "cannot assess", which is distinct from `0.0` for
"assessed, and it scores nothing". The score is computed over the assessed
components only, with their weight renormalised:

```text
score = 100 × Σ(value × weight) / Σ(weight)   over assessed components only
```

Each component reports an **effective weight** — what it actually counted for
after redistribution — alongside its configured weight.

`confidence` is the share of the configured weight that was assessable,
discounted by a factor (0.75) when the company record is itself stale per §61.

## Why

**Zeroing engagement would cap every prospect in the product at 90 for a whole
phase.** A ceiling nobody would think to look for, in a number everybody
would quote. It would also be invisible: 90 looks like a good score.

**Zeroing intent asserts something false.** "We looked and found no buying
signals" and "nobody has crawled this company" are different claims, and only
one of them is true of a freshly imported list. The first is a reason not to
call; the second is a reason to go and look.

**The alternative — requiring full data before scoring at all — makes the
product useless on day one.** A customer who imports 500 companies gets no
ranking until a crawl cycle completes, which is precisely when they most need
one.

**Redistribution keeps the configured weights meaningful as relative
importance.** A customer who sets intent to 40 means "intent matters twice as
much as ICP fit to me", not "40 of my 100 points come from intent even when
intent is unknowable". This is also what lets a component arrive later without
anybody re-tuning their weights.

## Consequences

- **Confidence is not decoration.** A score of 82 from three components is a
  different claim from 82 from eight, so the interface shows confidence on the
  row, not only in the panel, and the §119 payload lists what was not assessed
  with a human-readable reason for each.
- **Examining a company can lower its score while raising its confidence**, and
  that is correct. A thin assessment of a perfect-looking prospect is not a
  better assessment than a full one that finds no intent. A test asserts this
  explicitly, because the intuitive assertion ("more data, higher score") would
  have been asserting a bug.
- **A component that raises an exception is recorded as unassessed** rather than
  dropped, because dropping it would silently reweight everything else.
- **Weights are stored raw and normalised at scoring time**, so they need not
  total 100. A customer typing 10 into every box means "weigh these equally".
- **Changing the weighting rescores every stored lead.** Leaving them would
  mean a list sorted by one set of rules and explained by another.
- When Phase 3 lands, `score_engagement` is the single function to fill in.
  Nothing else changes.

## What this does not solve

Coverage is not accuracy. A prospect assessed on all eight components can
still be scored wrongly, because the component values are themselves
heuristics — a trigram industry match, a signal strength, an email status.
Confidence says how much of the question was answered, not how well. Only the
Phase 0 comparison the build plan calls for (does the machine find prospects
as good as the ones found by hand?) can answer the second, and it needs real
customers, not a unit test.
