# ADR 0010 — The reason-to-contact is two fields, and one of them is verified

**Status:** Accepted · **Date:** 2026-10-09

## Context

PRD §35 asks for one short explanation per high-priority prospect, with a
worked example:

> ABC Logistics recently expanded into Ghana and is hiring regional sales
> staff. Your sales automation product could help them manage the growing
> outbound team.

and one constraint: "The explanation must be evidence-based." The build plan
calls it "the highest-leverage string in the product — evidence-linked, never
a free-text LLM flourish."

The obvious implementation is a `TextField` the model fills in.

## Decision

It is stored as three parts, not one string:

- `reason_observation` — a claim of fact about the prospect;
- `reason_implication` — why that matters for what the seller sells;
- `reason_evidence` — quotes supporting the observation.

`reason_sentence` composes the first two for display. On every run,
`apps.intelligence.research_agents.verified_reason` checks that at least one
evidence quote appears verbatim (whitespace-insensitively) in the material the
model was shown. If none does, **the whole reason is discarded** and
`reason_rejected` records why.

Personalization points are verified the same way, each against its own
`source_quote`, and ungrounded entries in the general evidence list are
dropped.

## Why

**A single text field cannot carry the constraint.** Asked for one sentence, a
model produces a fluent sentence, and once it is a string there is nothing
left to check: fluency is indistinguishable from grounding. Split in two, the
factual half has a type of claim that can be verified and the persuasive half
is openly an argument.

**The split matches the PRD's own example.** "Recently expanded into Ghana and
is hiring regional sales staff" is the observation; "your sales automation
product could help them manage the growing outbound team" is the implication.
The example was already two sentences doing two different jobs.

**Only the observation is checked.** The implication is an inference about the
seller's own product, which is exactly what the seller is entitled to infer.
Demanding evidence for "our product would help you" would make the field
unfillable.

**Rejected whole, not trimmed.** Storing the implication without a verified
observation leaves a sales argument with nothing behind it — the free-text
flourish, arrived at by way of a partial save.

**A missing reason is a correct answer.** §35 says every high-priority prospect
*should* have an explanation, which tempts an implementation into always
producing one. A reason the material cannot support is worse than none,
because the customer discovers it in front of a buyer. `reason_rejected` keeps
the two cases apart: "nothing to say yet" and "the agent wrote something we
could not verify" call for different responses, and an empty field is
indistinguishable from either.

**An edit keeps the evidence.** A rep rewording an observation is rewording
the same fact. Clearing the evidence on edit would convert a checkable claim
into a flourish by way of a helpful feature.

## Consequences

- The research agent needs the signals' quoted evidence *in the prompt
  context*, not a summary of it. Without quotable material there is nothing to
  verify against and every reason would be rejected.
- The interface shows the quote and its source link directly under the
  sentence, never behind a disclosure. The server guarantees traceability; the
  interface has to make it unmissable.
- The prospect row carries `reason.rejected` as well as `reason.sentence`.
- Research is scoped by opportunity score (`RESEARCH_MIN_SCORE`, default 60)
  because it is an advanced-tier call per company. A person asking for one
  prospect by hand is never gated — they have already decided it is worth it.

## The limit, stated

**Grounding proves provenance, not truth.** A prospect's website can say
anything, including a sentence written to be quoted back, and a quote of it
*will* be found in the material because it is in the material. A test asserts
this behaviour rather than leaving it implied
(`test_a_quoted_injection_passes_grounding_and_this_is_the_known_limit`).

What stands between that and a customer repeating a planted claim is: the
prompt's standing instruction not to treat page content as fact-giving
instructions (an eval case covers it), and the quote plus source URL being on
the card so a human reads the claim before using it. The guarantee the code
makes is narrower than "true" and worth saying precisely: **no claim without a
traceable source.**
