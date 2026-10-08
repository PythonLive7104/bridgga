# ADR 0001 — Stack and framework versions

**Status:** Accepted · **Date:** 2026-10-08

## Context

The PRD specifies Django 5.x. The build toolchain on this machine runs Python
3.14, which Django 5.2 does not support.

## Decision

- **Django 6.0** (`>=6.0,<6.1`), not 5.2.
- Upper bound at 6.1 because `django-celery-beat` 2.9.0 requires `Django<6.1`.
- Python 3.13 in the container image; 3.14 works locally.

## Consequences

- Revisit the `<6.1` cap when django-celery-beat supports 6.1. The alternative
  was dropping database-backed periodic schedules, which later phases need for
  user-configurable campaign scheduling.
- Verified working together on Python 3.14: Django 6.0.9, DRF 3.18.3,
  django-allauth 65.19.7, Celery 5.6.3, psycopg 3.3.6.
