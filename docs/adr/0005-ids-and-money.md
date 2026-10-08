# ADR 0005 — Identifiers and money representation

**Status:** Accepted · **Date:** 2026-10-08

## Context

Both choices are near-impossible to change once data and API clients exist.

## Decision

**Identifiers.** Internal `BigAutoField` primary keys for join and index
performance; every row also carries an immutable `public_id` UUID, and that is
the only identifier the API exposes (PRD section 80). UUID primary keys would
widen every foreign-key index; sequential integers in URLs invite enumeration.

**Money.** Integer minor units (kobo, cents) plus a currency code. Floats lose
money, and one column cannot represent NGN and USD at once (PRD section 72
lists twelve currencies).

**Credits.** An append-only ledger, not a mutable balance column. A balance
that can be overwritten cannot be reconciled when a customer disputes it, and
concurrent AI jobs would race on it.

## Consequences

- API lookups are by `public_id`; `lookup_field` is set accordingly.
- Balance is a `SUM` over the ledger. If that becomes hot, add a cached
  projection — never a writable balance column.
