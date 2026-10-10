"""Shared Django settings.

Environment-specific modules (dev, prod, test) import from here and override.
Every value that differs between environments comes from the environment, not
from a conditional in this file.
"""

from __future__ import annotations

import os
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[2]

# backend/.env is the application's configuration, and it is loaded here --
# in the settings module every entrypoint imports -- rather than in manage.py.
# Loaded only from manage.py, it reached `runserver` and nothing else: not
# gunicorn, not the Celery worker, not beat. The worker would then run the
# same code against different settings from the web process, which is a
# difficult thing to notice and a worse thing to debug.
#
# `override=False` is the default and is the behaviour we want: a variable
# already set in the real environment wins. On a server the process manager
# supplies them; the file is the fallback.
# Captured before the file is read, so a settings module can tell a value that
# came from the real environment -- CI, a process manager, `docker compose` --
# from one that came out of backend/.env. The test settings depend on the
# difference: a developer's file points DATABASE_URL at a compose hostname,
# and that must not decide where the suite runs.
PROCESS_ENVIRON = dict(os.environ)

load_dotenv(BASE_DIR / ".env", override=False)

# One DATABASE_URL, two vantage points: `db` resolves inside the compose
# network and nowhere else, so the same file that works in Docker fails a
# `manage.py runserver` with "failed to resolve host 'db'". The names are
# corrected here, before anything reads them, and only under the dev settings
# -- quietly redirecting a production database to localhost would be a far
# worse failure than the one this prevents.
if os.environ.get("DJANGO_SETTINGS_MODULE", "").endswith(".dev"):
    from config.compose_hosts import localise_environment

    localise_environment()


def env(key: str, default: str | None = None) -> str:
    value = os.environ.get(key, default)
    if value is None:
        raise RuntimeError(f"Required environment variable {key} is not set")
    return value


def env_bool(key: str, default: bool = False) -> bool:
    return os.environ.get(key, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(key: str, default: str = "") -> list[str]:
    raw = os.environ.get(key, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


# --------------------------------------------------------------------------- #
# Core
# --------------------------------------------------------------------------- #

SECRET_KEY = env("DJANGO_SECRET_KEY", "insecure-dev-key-override-in-every-real-env")
DEBUG = False
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

AUTH_USER_MODEL = "accounts.User"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

SITE_ID = 1

# --------------------------------------------------------------------------- #
# Applications
# --------------------------------------------------------------------------- #

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Needed from Phase 2.9 for full-text search, trigram similarity and the
    # GIN indexes behind prospect discovery (ADR 0006 anticipated this point).
    # Harmless on SQLite: it contributes no models or tables, and the search
    # layer dispatches on the connection vendor.
    "django.contrib.postgres",
    "django.contrib.sites",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "corsheaders",
    "django_filters",
    "drf_spectacular",
    "django_celery_beat",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "allauth.socialaccount.providers.microsoft",
    "allauth.mfa",
    "allauth.headless",
]

LOCAL_APPS = [
    "apps.common",
    "apps.accounts",
    "apps.organizations",
    "apps.intelligence",
    "apps.companies",
    "apps.contacts",
    "apps.leads",
    "apps.ai",
    "apps.audit",
    "apps.billing",
    "apps.api",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "apps.common.middleware.RequestIDMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# --------------------------------------------------------------------------- #
# Database
# --------------------------------------------------------------------------- #
# DATABASE_URL drives everything. docker-compose and CI point it at Postgres;
# dev.py falls back to SQLite only so the project runs without Docker.

DATABASES = {
    "default": dj_database_url.parse(
        env("DATABASE_URL", f"sqlite:///{BASE_DIR / 'local.sqlite3'}"),
        conn_max_age=600,
        conn_health_checks=True,
    )
}

# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

# Argon2 first: stronger default than PBKDF2 (PRD section 74).
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# allauth: the whole of PRD section 23 except SSO/SAML, which is Phase 7.
ACCOUNT_LOGIN_METHODS = {"email"}
# Our User model has no username column (PRD section 23: email is the
# identity). Without this, allauth keeps its default of "username" and
# BaseSignupForm asks the model for a field that does not exist, so every
# signup request -- HTML or headless -- raises FieldDoesNotExist and
# returns a 500 before validation even begins.
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
# Name fields. SIGNUP_FIELDS above only understands allauth's own
# identifiers, so anything extra arrives through this form -- which
# BaseSignupForm inherits from, and which the headless API therefore
# picks up as well, so the JSON endpoint accepts and stores them too.
ACCOUNT_SIGNUP_FORM_CLASS = "apps.accounts.forms.SignupForm"
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
ACCOUNT_EMAIL_SUBJECT_PREFIX = ""
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_PREVENT_ENUMERATION = True
ACCOUNT_RATE_LIMITS = {
    "login_failed": "5/5m/ip,5/5m/key",
    "signup": "10/h/ip",
    "reset_password": "5/h/ip",
    "confirm_email": "5/h/key",
    "login_by_code": "5/h/key",
}
# Magic link / login-by-code.
ACCOUNT_LOGIN_BY_CODE_ENABLED = True
ACCOUNT_LOGIN_BY_CODE_TIMEOUT = 600

MFA_SUPPORTED_TYPES = ["totp", "recovery_codes"]
MFA_TOTP_ISSUER = env("MFA_TOTP_ISSUER", "Bridgga")

SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "APPS": [
            {
                "client_id": os.environ.get("GOOGLE_OAUTH_CLIENT_ID", ""),
                "secret": os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", ""),
                "key": "",
            }
        ],
        "SCOPE": ["profile", "email"],
        "AUTH_PARAMS": {"access_type": "offline"},
    },
    "microsoft": {
        "APPS": [
            {
                "client_id": os.environ.get("MICROSOFT_OAUTH_CLIENT_ID", ""),
                "secret": os.environ.get("MICROSOFT_OAUTH_CLIENT_SECRET", ""),
                "settings": {"tenant": os.environ.get("MICROSOFT_OAUTH_TENANT", "common")},
            }
        ],
    },
}
SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True

# Headless mode: the Next.js app is the only client, so allauth serves JSON.
HEADLESS_ONLY = True
FRONTEND_URL = env("FRONTEND_URL", "http://localhost:3000")
HEADLESS_FRONTEND_URLS = {
    "account_confirm_email": f"{FRONTEND_URL}/auth/verify-email/{{key}}",
    "account_reset_password": f"{FRONTEND_URL}/auth/reset-password",
    "account_reset_password_from_key": f"{FRONTEND_URL}/auth/reset-password/{{key}}",
    "account_signup": f"{FRONTEND_URL}/auth/signup",
    "socialaccount_login_error": f"{FRONTEND_URL}/auth/social-error",
}

# --------------------------------------------------------------------------- #
# DRF
# --------------------------------------------------------------------------- #

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "apps.common.pagination.CursorPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.common.exceptions.api_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": [
        "apps.common.throttling.BurstRateThrottle",
        "apps.common.throttling.SustainedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "burst": env("THROTTLE_BURST", "60/min"),
        "sustained": env("THROTTLE_SUSTAINED", "2000/day"),
        # Public endpoints (free tools, contact forms) key on IP instead.
        "anon_burst": env("THROTTLE_ANON_BURST", "20/min"),
    },
    "DEFAULT_VERSIONING_CLASS": "rest_framework.versioning.NamespaceVersioning",
    "ALLOWED_VERSIONS": ["v1"],
    "DEFAULT_VERSION": "v1",
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Bridgga API",
    "DESCRIPTION": "AI Customer Acquisition OS — tenant-scoped REST API.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": "/api/v[0-9]",
    "COMPONENT_SPLIT_REQUEST": True,
    "SORT_OPERATIONS": True,
    "ENUM_NAME_OVERRIDES": {
        "RoleEnum": "apps.organizations.roles.Role.choices",
    },
}

# --------------------------------------------------------------------------- #
# Celery
# --------------------------------------------------------------------------- #

REDIS_URL = env("REDIS_URL", "redis://localhost:6379/0")

CELERY_BROKER_URL = env("CELERY_BROKER_URL", REDIS_URL)
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", REDIS_URL)
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TIMEZONE = "UTC"
CELERY_ENABLE_UTC = True
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_TIME_LIMIT = 30 * 60
CELERY_TASK_SOFT_TIME_LIMIT = 25 * 60
CELERY_BROKER_TRANSPORT_OPTIONS = {"visibility_timeout": 3600}
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

# Dedicated queues so a slow crawl or a long AI job cannot starve message
# delivery (PRD sections 81 and 104).
CELERY_TASK_DEFAULT_QUEUE = "default"
CELERY_TASK_QUEUES_NAMES = ["default", "crawl", "enrich", "ai", "send", "analytics"]
# How long a sourced fact is trusted before it is shown as stale (PRD section
# 61 keeps `last_verified_at` for exactly this). A prospect researched six
# months ago may have moved, been acquired, or stopped existing.
DATA_FRESHNESS_DAYS = int(env("DATA_FRESHNESS_DAYS", "90"))

# Opportunity score a lead must reach before the research agent is run over it
# automatically (PRD section 34, "for high-value prospects"). An advanced-tier
# model call per company is not something to spend on a whole imported list.
# A person asking for one prospect by hand is never gated by this.
RESEARCH_MIN_SCORE = int(env("RESEARCH_MIN_SCORE", "60"))

# How long a website audit is reused for the same URL (PRD sections 17, 49).
# The audit is a public endpoint that crawls a site and calls a paid model, so
# without a window it is a way to spend our money and somebody else's
# bandwidth one refresh at a time.
WEBSITE_AUDIT_CACHE_MINUTES = int(env("WEBSITE_AUDIT_CACHE_MINUTES", "60"))

CELERY_TASK_ROUTES = {
    # Declared before the wildcard below, which would otherwise claim it:
    # Celery returns the first matching pattern, and dicts keep insertion
    # order. This task does crawl, but the slow, rate-limited, costly part is
    # the model call, and running it behind a crawl backlog makes onboarding
    # look broken.
    "apps.intelligence.tasks.analyze_company_website": {"queue": "ai"},
    # Research makes no outbound requests at all -- everything it reads is
    # already stored -- so it belongs with the other model calls rather than
    # behind a crawl backlog.
    "apps.intelligence.tasks.research_prospect": {"queue": "ai"},
    "apps.intelligence.tasks.research_top_prospects": {"queue": "ai"},
    "apps.intelligence.tasks.*": {"queue": "crawl"},
    # Same ordering rule as above: the specific signal tasks are declared
    # before the companies wildcard that would otherwise claim them. One
    # fetches prospect websites and belongs on the crawl worker with its
    # egress allowlist; the other calls a paid model and must not be able to
    # stall behind a diffing backlog.
    "apps.companies.tasks.refresh_company_signals": {"queue": "crawl"},
    "apps.companies.tasks.interpret_company_website_change": {"queue": "ai"},
    "apps.companies.tasks.*": {"queue": "enrich"},
    "apps.leads.tasks.*": {"queue": "enrich"},
    "apps.ai.tasks.*": {"queue": "ai"},
    "apps.messaging.tasks.*": {"queue": "send"},
    "apps.analytics.tasks.*": {"queue": "analytics"},
}

# --------------------------------------------------------------------------- #
# Cache
# --------------------------------------------------------------------------- #

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env("CACHE_URL", REDIS_URL),
        "KEY_PREFIX": "bridgga",
    }
}

# --------------------------------------------------------------------------- #
# Static / media
# --------------------------------------------------------------------------- #

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# --------------------------------------------------------------------------- #
# Uploads (PRD section 110)
# --------------------------------------------------------------------------- #

# Anything larger than this is streamed to a temporary file rather than held in
# memory, so one upload cannot exhaust a worker.
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
# A guard against a request with a vast number of small fields, which is cheap
# to send and expensive to parse.
DATA_UPLOAD_MAX_NUMBER_FIELDS = 1_000

#: Hard ceiling on an imported file. Generous for a prospect list and far below
#: anything that would threaten the worker parsing it.
IMPORT_MAX_BYTES = int(env("IMPORT_MAX_BYTES", str(20 * 1024 * 1024)))

#: Rows read from one file. A list longer than this is a data-provider feed,
#: which belongs on the API rather than in an upload form.
IMPORT_MAX_ROWS = int(env("IMPORT_MAX_ROWS", "50000"))

#: Content types accepted for an import. Checked against the file's own
#: declared type *and* its extension, because either alone is trivially lied
#: about and the parser is chosen from this.
IMPORT_ALLOWED_TYPES = {
    "text/csv": ".csv",
    "application/csv": ".csv",
    "text/plain": ".csv",
    "application/vnd.ms-excel": ".csv",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
}

# --------------------------------------------------------------------------- #
# i18n
# --------------------------------------------------------------------------- #

LANGUAGE_CODE = "en"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
LANGUAGES = [("en", "English"), ("fr", "French"), ("ar", "Arabic")]
LOCALE_PATHS = [BASE_DIR / "locale"]

# --------------------------------------------------------------------------- #
# Security
# --------------------------------------------------------------------------- #

CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", FRONTEND_URL)
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", FRONTEND_URL)

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_NAME = "bridgga_session"
SESSION_ENGINE = "django.contrib.sessions.backends.db"
CSRF_COOKIE_HTTPONLY = False  # the SPA must read it to echo X-CSRFToken
CSRF_COOKIE_SAMESITE = "Lax"

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
X_FRAME_OPTIONS = "DENY"

DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "no-reply@localhost")
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# --------------------------------------------------------------------------- #
# Logging (structlog -> JSON on stdout)
# --------------------------------------------------------------------------- #

from config.logging import configure_structlog, logging_config  # noqa: E402

LOGGING = logging_config(env("LOG_LEVEL", "INFO"))
configure_structlog()

# --------------------------------------------------------------------------- #
# Application settings
# --------------------------------------------------------------------------- #

# Header the SPA uses to pick the active organization. Membership is always
# re-verified server side; this header only selects, it never authorises.
ORGANIZATION_HEADER = "X-Organization"

# The admin lives at a non-guessable prefix in real environments.
ADMIN_URL_PREFIX = env("ADMIN_URL_PREFIX", "admin").strip("/")

# --------------------------------------------------------------------------- #
# AI (PRD sections 56 to 59)
# --------------------------------------------------------------------------- #

# Blank auto-detects: the real provider when ANTHROPIC_API_KEY is set, the
# deterministic stub otherwise. That keeps CI and a fresh checkout working
# without credentials, and stops a test spending money by accident.
AI_PROVIDER = os.environ.get("AI_PROVIDER", "")

# Per-tier model routing override. Cheap models handle classification and
# extraction; advanced models handle research and strategy. Setting a tier here
# imposes a cost ceiling without a code change.
AI_MODEL_TIERS = {
    key: value
    for key, value in {
        "cheap": os.environ.get("AI_MODEL_CHEAP", ""),
        "standard": os.environ.get("AI_MODEL_STANDARD", ""),
        "advanced": os.environ.get("AI_MODEL_ADVANCED", ""),
    }.items()
    if value
}
