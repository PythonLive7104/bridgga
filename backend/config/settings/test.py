"""Test settings.

Kept deliberately close to prod in behaviour and only fast where speed cannot
hide a bug. Password hashing is weakened and Celery runs inline; authorisation,
tenancy and validation all behave exactly as in production.
"""

from __future__ import annotations

from .base import *
from .base import BASE_DIR, PROCESS_ENVIRON

DEBUG = False
SECRET_KEY = "test-only-secret-key"
ALLOWED_HOSTS = ["testserver", "localhost"]

# CI sets DATABASE_URL to Postgres. Locally this falls back to SQLite so the
# suite runs without Docker -- see docs/adr/0006-sqlite-dev-fallback.md.
#
# Read from PROCESS_ENVIRON, not os.environ: backend/.env is loaded into the
# process by then, and a developer's file points at the compose hostname `db`,
# which does not resolve outside that network. Tests would fail to connect on
# a machine where the application itself runs perfectly. What runs the suite
# is a deliberate choice by whoever invoked it, never a side effect of local
# configuration.
DATABASES = {
    "default": __import__("dj_database_url").parse(
        PROCESS_ENVIRON.get("DATABASE_URL") or f"sqlite:///{BASE_DIR / 'test.sqlite3'}",
    )
}

# The stub provider, always, whatever backend/.env says.
#
# This is a spend control, not a speed one. Celery runs eagerly here, so a test
# that posts to /company-profile/analyze runs the agent inline, and an agent
# called without an explicit provider asks the registry for one. With
# AI_PROVIDER=openai and a real key in backend/.env -- the normal state of a
# working machine -- that is a live, billed API call on every run of the suite,
# with no indication in the output that money was spent.
#
# Tests that want a real model call ask for one explicitly: mark them `live_ai`
# and run with --live-ai. See tests/conftest.py.
AI_PROVIDER = "stub"

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Rate limits are asserted by their own tests, which enable them explicitly.
# Leaving them on globally makes every other test order-dependent.
# `False`, not `{}`. An empty dict is *merged over* allauth's defaults and
# disables nothing, so signup stayed capped at 20/m/ip and the suite tripped
# it once enough tests signed in within a minute -- intermittently, and only
# in the slower environment, which is the worst way for a test to fail.
# `False` is the documented switch that turns the whole mechanism off.
#
# The limits themselves are production behaviour and are worth testing; that
# belongs in a test that sets them deliberately, not in every other one.
ACCOUNT_RATE_LIMITS = False

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
