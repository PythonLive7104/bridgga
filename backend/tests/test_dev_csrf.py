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


def test_the_patch_covers_the_api_as_well_as_the_middleware() -> None:
    """DRF builds its own CSRF checker, so a middleware swap misses every write.

    This is the bug the first attempt had: allauth endpoints accepted the LAN
    origin and `POST /api/v1/organizations` still answered 403, because
    SessionAuthentication constructs CSRFCheck directly.
    """
    from django.middleware.csrf import CsrfViewMiddleware
    from rest_framework.authentication import CSRFCheck

    from apps.common.dev_middleware import install_private_network_trust

    install_private_network_trust()

    # One method, inherited by both, so neither path can be left behind.
    assert CSRFCheck._origin_verified is CsrfViewMiddleware._origin_verified


def test_installing_twice_does_not_stack_wrappers() -> None:
    """Django re-imports app configs in some flows; this must stay idempotent."""
    from django.middleware.csrf import CsrfViewMiddleware

    from apps.common.dev_middleware import install_private_network_trust

    install_private_network_trust()
    first = CsrfViewMiddleware._origin_verified
    install_private_network_trust()

    assert CsrfViewMiddleware._origin_verified is first


def test_the_relaxation_is_inert_when_debug_is_off(settings: object) -> None:
    """Belt and braces: prod never installs this, and it would do nothing anyway."""
    from django.middleware.csrf import CsrfViewMiddleware
    from django.test import override_settings

    from apps.common.dev_middleware import install_private_network_trust

    install_private_network_trust()
    middleware = CsrfViewMiddleware(lambda request: None)

    with override_settings(DEBUG=False):
        assert not middleware._origin_verified(
            _StubRequest({"HTTP_ORIGIN": "http://192.168.1.50:3000"})
        )


def test_a_private_origin_is_accepted_when_debug_is_on() -> None:
    from django.middleware.csrf import CsrfViewMiddleware
    from django.test import override_settings

    from apps.common.dev_middleware import install_private_network_trust

    install_private_network_trust()
    middleware = CsrfViewMiddleware(lambda request: None)

    with override_settings(DEBUG=True):
        assert middleware._origin_verified(
            _StubRequest({"HTTP_ORIGIN": "http://192.168.1.50:3000"})
        )
        assert not middleware._origin_verified(
            _StubRequest({"HTTP_ORIGIN": "http://evil.example.com"})
        )


class _StubRequest:
    """Enough of a request for the parent's origin check to run and fail."""

    def __init__(self, meta: dict) -> None:
        self.META = meta

    def get_host(self) -> str:
        return "testserver"

    def is_secure(self) -> bool:
        return False
