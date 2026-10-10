# ADR 0012 — Suppression matches on a hash, and the send path has one door

**Status:** Accepted · **Date:** 2026-10-10

## Context

PRD §63 asks for four things when somebody says stop:

1. suppress them immediately;
2. prevent accidental re-enrollment;
3. record the timestamp;
4. "preserve minimum data necessary to honor suppression obligations".

The fourth sits oddly beside §62's requirement to support deletion, and the
tension is real: **if a person asks to be deleted and we delete their address,
we lose the means of recognising them, so the next import adds them back and
the next campaign contacts them.**

Separately, the build plan requires the suppression check to be "a mandatory
suppression check in the send path that cannot be bypassed", and there is as
yet no send path to put it in.

## Decision

**Match on `sha256` of the normalised address, not the address.**
`SuppressionEntry` stores `value_hash` (the matching key, never null) and
`value` (plaintext, for the customer's own list, redactable). Erasure clears
`value` and keeps `value_hash`.

**Suppression is organization-wide and never cross-tenant.** One customer's
unsubscribe covers every campaign, workspace and channel they run, and touches
no other customer.

**Suppressing also marks the matching `Person` records unsubscribed.** The
list is authoritative at send time; the contact status is a denormalised copy
so suppressed people leave audiences, estimates and the "reachable today"
filter.

**One guard, plus an architecture test.** `apps.compliance.guard` is the only
way to decide whether an address may be contacted, and a test fails the build
if any module outside an explicit allowlist constructs outbound mail.

**Entries recording a person's decision cannot be deleted.** `unsubscribed`,
`complained` and `legal_request` are permanent; `manual`, `imported` and
`bounced` can be corrected.

**Unknown markets fail closed.** `policy_for` returns a strict default.

## Why

**Hashing resolves §63's apparent contradiction exactly.** Both requirements
hold at once: the personal data is gone, and the person is still recognised.
Nothing else does — keeping the address defeats erasure, deleting it defeats
suppression.

**Normalising is where suppression lists actually fail.** Not a missing check:
a webhook sends a bare address, an import sends `"Ada Obi" <ADA@X.com>`, a
reply header sends angle brackets. If those produce different keys the person
is suppressed under one spelling and contactable under another. Lowercase,
trim and unwrap the display name — and deliberately *not* Gmail's dot and plus
rules, which would silently suppress addresses nobody asked to suppress on
every other provider.

**The architecture test covers what no unit test can.** Every unit test here
asserts the guard blocks what it is given; none can assert that a campaign
sender written next month calls it. Scanning for `send_mail`,
`EmailMessage` and friends outside the delivery layer fails at the moment the
question is cheap to ask.

**A permanent entry is not paternalism.** A button that deletes an unsubscribe
has exactly one use. A mistyped manual row is a different thing, and can be
corrected.

## Consequences

- The send path, when it exists, must call `assert_sendable` or `partition`
  and nothing else. `partition` is one query for a whole audience, because the
  §36 pre-launch panel needs "412 recipients, 37 suppressed" before approval
  and the scheduler needs it again at send time.
- Unsubscribe links are signed and **never expire**. A March link must work in
  November, because the person reading it then is the one who otherwise
  reports the sender. Nothing is stored, so an opt-out works after the
  campaign, message or contact has been deleted.
- The one-click POST is CSRF-exempt by necessity (RFC 8058; the request comes
  from a mailbox provider with no cookie). The exposure is bounded: holding a
  signed token lets you stop mail to the address inside it and nothing else.
- The public endpoint answers identically for valid and invalid tokens on
  POST, so it cannot be used to test addresses.
- `RegionalPolicy` is platform reference data, like `CountryProfile`. The
  seeded values are a conservative starting point for the legal review §62
  requires, not the review; where a regime is contested the stricter reading is
  recorded, with the reasoning in the row's notes.
