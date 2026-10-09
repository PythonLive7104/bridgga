"""Local development settings."""

from __future__ import annotations

import os

from .base import *
from .base import INSTALLED_APPS, REST_FRAMEWORK, env_list

DEBUG = True

INSTALLED_APPS = [*INSTALLED_APPS, "django_extensions"]

# Browsable API is handy locally and off everywhere else.
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
}


# --------------------------------------------------------------------------- #
# Reaching the dev server from another device on the network
# --------------------------------------------------------------------------- #
#
# Opening the app on a phone, or from a second machine, gives a browser origin
# like http://192.168.1.50:3000. Django rejects that on every POST -- "Origin
# checking failed" -- and answers with an HTML 403, so every form on the site
# looks broken with no stated reason.
#
# Listing the address in CSRF_TRUSTED_ORIGINS does not survive the next DHCP
# lease, and cannot be derived inside a container at all: the backend sees its
# own 172.x address, never the host's. So the rule is the property -- a
# literal private or loopback address -- applied by a middleware that only
# exists in this settings module.

TRUST_PRIVATE_NETWORK_CSRF = True

# Any host, because the address this is reached on is not knowable here and
# DEBUG is True. Set DJANGO_ALLOWED_HOSTS to pin it.
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "") or ["*"]

# --------------------------------------------------------------------------- #
# Email
# --------------------------------------------------------------------------- #
#
# Base prints mail to the console, which is fine without Docker. With the
# compose stack there is a MailHog on EMAIL_HOST, and account verification is
# mandatory -- so printing the link into a container's log, where nobody is
# looking, means a new account can be created and then never signed in to.
# Signup looks broken and the cause is three services away.

# Verification stays mandatory by default, matching production. Set
# ACCOUNT_EMAIL_VERIFICATION=optional while no mail provider is configured, so
# a new account is usable immediately; `manage.py verify_email <address>`
# confirms an account that already exists.
ACCOUNT_EMAIL_VERIFICATION = os.environ.get("ACCOUNT_EMAIL_VERIFICATION", "mandatory")

if os.environ.get("EMAIL_HOST"):
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = os.environ["EMAIL_HOST"]
    EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "1025"))
    EMAIL_USE_TLS = False  # MailHog speaks plain SMTP.

# Without Docker there is no local Redis, so fall back to in-process backends.
# Set REDIS_URL (or run infra/docker-compose.yml) to exercise the real thing.
if not os.environ.get("REDIS_URL"):
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    CELERY_TASK_ALWAYS_EAGER = True
    CELERY_TASK_EAGER_PROPAGATES = True
