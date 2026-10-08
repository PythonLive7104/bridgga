"""Production settings.

Everything here fails loudly rather than degrading quietly: a missing secret
should stop a deploy, not ship an insecure default.
"""

from __future__ import annotations

import os

import sentry_sdk
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.django import DjangoIntegration

from .base import *
from .base import BASE_DIR, env, env_bool, env_list  # noqa: F401

DEBUG = False

# No default: a production deploy without an explicit secret must not start.
SECRET_KEY = env("DJANGO_SECRET_KEY")
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS")
if not ALLOWED_HOSTS:
    raise RuntimeError("DJANGO_ALLOWED_HOSTS must be set in production")

DATABASES = {
    "default": __import__("dj_database_url").parse(
        env("DATABASE_URL"),
        conn_max_age=600,
        conn_health_checks=True,
        ssl_require=env_bool("DATABASE_SSL_REQUIRE", True),
    )
}

# --------------------------------------------------------------------------- #
# Transport security (PRD section 74)
# --------------------------------------------------------------------------- #

SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 365
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# --------------------------------------------------------------------------- #
# Object storage
# --------------------------------------------------------------------------- #

STORAGES = {
    "default": {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": env("AWS_STORAGE_BUCKET_NAME"),
            "region_name": env("AWS_S3_REGION_NAME", "eu-west-1"),
            "endpoint_url": os.environ.get("AWS_S3_ENDPOINT_URL") or None,
            "default_acl": "private",
            "querystring_auth": True,
            "file_overwrite": False,
            # Uploaded files are randomised and private (PRD section 110).
            "signature_version": "s3v4",
        },
    },
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# --------------------------------------------------------------------------- #
# Email
# --------------------------------------------------------------------------- #

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("EMAIL_HOST")
EMAIL_PORT = int(env("EMAIL_PORT", "587"))
EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)

# --------------------------------------------------------------------------- #
# Error reporting
# --------------------------------------------------------------------------- #

SENTRY_DSN = os.environ.get("SENTRY_DSN")
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=env("SENTRY_ENVIRONMENT", "production"),
        release=os.environ.get("GIT_SHA"),
        integrations=[DjangoIntegration(), CeleryIntegration()],
        traces_sample_rate=float(env("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
        # Prospect and conversation data is customer PII; never ship request
        # bodies or user records to a third party by default (PRD section 62).
        send_default_pii=False,
    )
