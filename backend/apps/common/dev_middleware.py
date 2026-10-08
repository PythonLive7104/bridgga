"""Development-only middleware.

Nothing here may be loaded in production. ``config.settings.dev`` installs it;
``config.settings.prod`` does not, and the check in ``PrivateNetworkCsrf``
refuses to do anything when ``DEBUG`` is False as a second line of defence.
"""

from __future__ import annotations

import ipaddress
from typing import Any
from urllib.parse import urlsplit

from django.conf import settings
from django.middleware.csrf import CsrfViewMiddleware


def is_private_origin(origin: str) -> bool:
    """True when ``origin`` points at a loopback or private-network address.

    Hostnames are rejected outright. Only a literal address counts, so a
    public name that happens to resolve inward cannot slip through, and no DNS
    lookup happens on the request path.
    """
    try:
        parsed = urlsplit(origin)
    except ValueError:
        return False

    if parsed.scheme not in {"http", "https"}:
        return False

    host = parsed.hostname
    if not host:
        return False

    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        # A name, not an address. localhost is already handled by the
        # ordinary CSRF_TRUSTED_ORIGINS entries.
        return False

    return address.is_loopback or address.is_private or address.is_link_local


class PrivateNetworkCsrf(CsrfViewMiddleware):
    """Trust CSRF origins on the local network, in development only.

    Opening the dev server from a phone, or from a second machine, produces an
    origin like ``http://192.168.1.50:3000``. Django rejects it on every POST
    and answers with an HTML 403, so every form on the site appears broken for
    no stated reason.

    The usual fix is to list the address in ``CSRF_TRUSTED_ORIGINS``, which
    does not survive the next DHCP lease, and cannot be derived inside a
    container: the backend sees its own ``172.x`` address, never the host's.

    So the rule is the property itself -- a literal private or loopback
    address -- rather than a list of them. This is safe here and nowhere else:
    on a public deployment the attacker's origin is a public name, which this
    still refuses, but the setting that gates it is ``DEBUG`` and this
    middleware is simply not installed in production.
    """

    def _origin_verified(self, request: Any) -> bool:
        if super()._origin_verified(request):
            return True
        if not settings.DEBUG:
            return False
        return is_private_origin(request.META.get("HTTP_ORIGIN", ""))
