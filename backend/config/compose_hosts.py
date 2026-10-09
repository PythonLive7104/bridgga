"""Rewrite compose service names to localhost when they cannot be resolved.

``backend/.env`` holds one ``DATABASE_URL``, and its host depends on where the
process happens to be running: ``db`` inside the compose network, ``localhost``
for a ``manage.py runserver`` on the machine itself. Asking a developer to edit
the file every time they switch is a footgun that fires as
``failed to resolve host 'db'`` -- a stack trace that says nothing about the
actual mistake.

So the names are corrected when, and only when, they do not resolve. The
service is published on the same port on the host, so the rewritten URL reaches
exactly the same database.

Deliberately narrow:

* only the names this project's own compose file defines, so an unresolvable
  hostname that is genuinely a typo or an outage still fails loudly
* only when resolution fails, so being inside the network changes nothing
* only from the dev settings module, never prod -- silently redirecting a
  production database to localhost is a far worse failure than the one this
  prevents
"""

from __future__ import annotations

import os
import socket
from urllib.parse import urlsplit, urlunsplit

#: Service names in infra/docker-compose.yml that something connects *to*.
COMPOSE_SERVICE_HOSTS = frozenset({"db", "redis", "mailhog", "storage"})

#: Environment variables holding a URL whose host may need correcting.
URL_VARIABLES = (
    "DATABASE_URL",
    "REDIS_URL",
    "CACHE_URL",
    "CELERY_BROKER_URL",
    "CELERY_RESULT_BACKEND",
    "AWS_S3_ENDPOINT_URL",
)

#: Variables holding a bare hostname rather than a URL.
HOST_VARIABLES = ("EMAIL_HOST",)


def resolves(host: str) -> bool:
    try:
        socket.getaddrinfo(host, None)
    except OSError:
        return False
    return True


def localise_url(url: str) -> str:
    """Swap a known compose hostname for localhost, keeping everything else."""
    if not url:
        return url

    try:
        parts = urlsplit(url)
    except ValueError:
        return url

    host = parts.hostname
    if host is None or host not in COMPOSE_SERVICE_HOSTS or resolves(host):
        return url

    # Rebuild the authority by hand: credentials and port must survive, and
    # replacing the host inside netloc by string substitution would also hit a
    # password that happened to contain the same word.
    userinfo = ""
    if parts.username:
        userinfo = parts.username
        if parts.password:
            userinfo += f":{parts.password}"
        userinfo += "@"

    port = f":{parts.port}" if parts.port else ""
    return urlunsplit(
        (parts.scheme, f"{userinfo}localhost{port}", parts.path, parts.query, parts.fragment)
    )


def localise_environment(environ: dict[str, str] | None = None) -> list[str]:
    """Correct every compose hostname in the environment. Returns what changed."""
    target = os.environ if environ is None else environ
    changed: list[str] = []

    for name in URL_VARIABLES:
        current = target.get(name)
        if not current:
            continue
        replacement = localise_url(current)
        if replacement != current:
            target[name] = replacement
            changed.append(name)

    for name in HOST_VARIABLES:
        current = target.get(name)
        if current in COMPOSE_SERVICE_HOSTS and not resolves(current):
            target[name] = "localhost"
            changed.append(name)

    return changed
