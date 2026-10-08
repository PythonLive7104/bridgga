"""The development-only private-network CSRF relaxation.

This widens a security control, so what matters is the boundary: it must
accept a literal private address and refuse everything else, including the
shapes an attacker would reach for first.
"""

from __future__ import annotations

import pytest

from apps.common.dev_middleware import is_private_origin


@pytest.mark.parametrize(
    "origin",
    [
        "http://192.168.1.50:3000",
        "http://192.168.18.2:3001",
        "http://10.0.0.8:8000",
        "http://172.16.4.2:3000",
        "http://127.0.0.1:3000",
        "https://192.168.1.50:3000",
        "http://[::1]:3000",
        "http://169.254.10.10:3000",  # link-local
    ],
)
def test_private_and_loopback_addresses_are_trusted(origin: str) -> None:
    assert is_private_origin(origin)


@pytest.mark.parametrize(
    "origin",
    [
        "http://evil.example.com",
        "https://bridgga.com",
        "http://8.8.8.8",
        # A name that *resolves* inward is still refused: only a literal
        # address counts, so there is no DNS-rebinding window here.
        "http://localtest.me:3000",
        "http://192.168.1.50.evil.com",
        # Non-web schemes have no business being an origin.
        "file://192.168.1.50",
        "javascript://192.168.1.50",
        "",
        "not a url",
        "null",
    ],
)
def test_everything_else_is_refused(origin: str) -> None:
    assert not is_private_origin(origin)


def test_the_relaxation_is_inert_when_debug_is_off(settings: object) -> None:
    """Belt and braces: prod never installs this, and it would do nothing anyway."""
    from unittest.mock import Mock

    from django.test import override_settings

    from apps.common.dev_middleware import PrivateNetworkCsrf

    middleware = PrivateNetworkCsrf(lambda request: None)
    request = Mock()
    request.META = {"HTTP_ORIGIN": "http://192.168.1.50:3000"}

    with override_settings(DEBUG=False):
        # The parent refuses it, and the override declines to help.
        assert not PrivateNetworkCsrf._origin_verified(middleware, _StubRequest(request.META))


class _StubRequest:
    """Enough of a request for the parent's origin check to run and fail."""

    def __init__(self, meta: dict) -> None:
        self.META = meta

    def get_host(self) -> str:
        return "testserver"

    def is_secure(self) -> bool:
        return False
