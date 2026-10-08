"""Test settings.

Kept deliberately close to prod in behaviour and only fast where speed cannot
hide a bug. Password hashing is weakened and Celery runs inline; authorisation,
tenancy and validation all behave exactly as in production.
"""

from __future__ import annotations

from .base import *
from .base import BASE_DIR, env

DEBUG = False
SECRET_KEY = "test-only-secret-key"
ALLOWED_HOSTS = ["testserver", "localhost"]

# CI sets DATABASE_URL to Postgres. Locally this falls back to SQLite so the
# suite runs without Docker -- see docs/adr/0006-sqlite-dev-fallback.md.
DATABASES = {
    "default": __import__("dj_database_url").parse(
        env("DATABASE_URL", f"sqlite:///{BASE_DIR / 'test.sqlite3'}"),
    )
}

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Rate limits are asserted by their own tests, which enable them explicitly.
# Leaving them on globally makes every other test order-dependent.
ACCOUNT_RATE_LIMITS = {}

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
