"""Local development settings."""

from __future__ import annotations

from .base import *
from .base import INSTALLED_APPS, REST_FRAMEWORK, env_list

DEBUG = True
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,0.0.0.0")

INSTALLED_APPS = [*INSTALLED_APPS, "django_extensions"]

# Browsable API is handy locally and off everywhere else.
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
}

# Without Docker there is no local Redis, so fall back to in-process backends.
# Set REDIS_URL (or run infra/docker-compose.yml) to exercise the real thing.
import os  # noqa: E402

if not os.environ.get("REDIS_URL"):
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    CELERY_TASK_ALWAYS_EAGER = True
    CELERY_TASK_EAGER_PROPAGATES = True
