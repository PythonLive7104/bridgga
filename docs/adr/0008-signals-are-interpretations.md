# ADR 0008 — A signal is an interpretation; an event is a fact

**Status:** Accepted · **Date:** 2026-10-09

## Context

Phase 2.7 created `companies.CompanyEvent`: something observable that happened
at a company, with provenance. Phase 2.10 needed `LeadSignal` from PRD §33,
which stores type, source, timestamp, confidence, evidence and
expiration/staleness.

On the field list the two are nearly identical, and the cheap move was to add
`expires_at` and `confidence` to `CompanyEvent` and be done.

## Decision

They stay separate models, with a foreign key from the signal to the event it
was derived from.

- **`CompanyEvent` is a fact about the world.** "Acme closed a Series A on 3
  March" is as true in 2031 as in 2026. Events are permanent history and have
  no expiry.
- **`LeadSignal` is a claim that something makes a company worth contacting
  *now*.** It carries `expires_at`, a `strength`, a decay curve, a `detector`
  that produced it, and a `dismissed_at` for when a human disagrees.

A detector that reads a dated event emits a signal pointing back at it
(`EventSignalDetector`). Detectors that read website snapshots emit signals
pointing at the snapshot instead.

## Why

The merged model cannot answer either question properly.

**An event with an expiry is a lie about history.** Expiring the Series A row
means losing the record that it happened, so a merged model has to keep
expired rows and filter them everywhere — which is a signal table with extra
steps, minus the ability to say *why* a row stopped counting.

**A signal without an expiry is the failure §33 exists to prevent.** Funding
from three years ago would sit at the top of a prospect list forever.

**One event can produce several signals, and one signal several events.** A
funding round is a funding signal today and a hiring signal when the roles
appear. The same hiring observation re-read next week is the same signal, not
a second one — which is what `fingerprint` and the uniqueness constraint on
`(company, signal_type, fingerprint)` encode.

**Dismissal belongs to the interpretation, not the fact.** "This is not
relevant to us" is a verdict on our inference, not a denial that the company
raised money. Putting `dismissed_at` on an event would conflate the two.

## Consequences

- The §29 prospect filters query `signals`, not `events`, and exclude expired
  and dismissed rows by default. `include_stale_signals` opts back in for
  research. The filter is built as a single `Q` applied in one `filter()` call
  so the type and the liveness describe the same row; split across two calls,
  Django joins the relation twice and a company with an expired funding signal
  and a live hiring signal matches "live funding signal".
- The prospect table's signal column shows live signals only.
- Re-detection extends a signal's life **only** when the detector marks it
  `renewable` — true for an open role still on the page, false for a stated
  past event. Without that distinction every crawl would renew "we raised
  $4M" and the expiry would be decorative.
- Expired signals are pruned on a schedule; **dismissed ones are kept**,
  because a dismissal is the only record of a human's verdict on a detector.
- Scoring (§32) reads `decayed_strength`, not `strength`, so age is priced in
  one place rather than at each call site.

## The AI boundary

Detection is deterministic and free. Diffing two strings does not need a
language model, and paying for one per prospect per day is indefensible at
volume. One model-backed interpreter (`signal_agents.interpret_website_change`)
runs *after* a deterministic detector has established that something
non-cosmetic changed, is shown only the diff, and has its output verified in
code: every interpreted signal must quote the supplied diff verbatim or it is
discarded. The prompt asks for grounding; this enforces it. Website content is
attacker-controlled, so the check cannot live only in the prompt.

The residual limitation, stated rather than hidden: grounding proves
provenance, not truth. A page that *says* "we raised $50M" produces a quotable
funding signal whether or not it happened. That is why the quote and the source
link are on the card in the interface — the customer is the last check, and
they can only be that if they can see what the claim rests on.
