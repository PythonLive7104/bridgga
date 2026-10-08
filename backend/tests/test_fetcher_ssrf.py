"""SSRF controls on the website fetcher (PRD sections 108 and 109).

The platform fetches URLs that customers supply, so these tests are the
difference between a feature and a hole in the network. They run offline: IP
literals need no DNS, and anything that does is driven through a patched
resolver or a mock transport.
"""

from __future__ import annotations

import socket

import httpx
import pytest

from apps.intelligence.fetcher import (
    FetchError,
    UnsafeUrlError,
    _is_public_address,
    assert_url_is_safe,
    fetch_url,
)

pytestmark = pytest.mark.security


# --------------------------------------------------------------------------- #
# Address classification
# --------------------------------------------------------------------------- #

NON_PUBLIC_ADDRESSES = [
    "127.0.0.1",
    "127.0.0.2",
    "0.0.0.0",
    "10.0.0.1",
    "172.16.0.1",
    "172.31.255.255",
    "192.168.1.1",
    # Cloud instance metadata. The single most valuable SSRF target there is:
    # on a misconfigured host it hands out credentials.
    "169.254.169.254",
    "169.254.0.1",
    "100.64.0.1",  # CGNAT / shared address space
    "192.0.0.1",  # IETF protocol assignments
    "224.0.0.1",  # multicast
    "240.0.0.1",  # reserved
    "::1",  # IPv6 loopback
    "fe80::1",  # IPv6 link-local
    "fc00::1",  # IPv6 unique-local
    "::",  # unspecified
    "::ffff:127.0.0.1",  # loopback as IPv4-mapped IPv6
    "::ffff:169.254.169.254",  # metadata as IPv4-mapped IPv6
]

PUBLIC_ADDRESSES = ["8.8.8.8", "1.1.1.1", "93.184.216.34", "2606:2800:220:1:248:1893:25c8:1946"]


@pytest.mark.parametrize("address", NON_PUBLIC_ADDRESSES)
def test_non_public_addresses_are_rejected(address: str) -> None:
    assert _is_public_address(address) is False


@pytest.mark.parametrize("address", PUBLIC_ADDRESSES)
def test_public_addresses_are_accepted(address: str) -> None:
    assert _is_public_address(address) is True


def test_garbage_is_not_mistaken_for_an_address() -> None:
    assert _is_public_address("not-an-ip") is False
    assert _is_public_address("") is False


# --------------------------------------------------------------------------- #
# URL validation
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "gopher://example.com/",
        "dict://example.com:11211/",
        "ftp://example.com/",
        "javascript:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        "redis://example.com:6379/",
    ],
)
def test_only_http_and_https_are_allowed(url: str) -> None:
    with pytest.raises(UnsafeUrlError):
        assert_url_is_safe(url)


def test_credentials_in_url_are_rejected() -> None:
    # Some clients forward these to the target, turning SSRF into
    # authenticated SSRF.
    with pytest.raises(UnsafeUrlError, match="credentials"):
        assert_url_is_safe("https://user:secret@93.184.216.34/")


@pytest.mark.parametrize("port", [22, 25, 3306, 5432, 6379, 8080, 8443, 9200, 11211])
def test_non_web_ports_are_rejected(port: int) -> None:
    """Blocking other ports removes internal service probing wholesale."""
    with pytest.raises(UnsafeUrlError, match="ports"):
        assert_url_is_safe(f"http://93.184.216.34:{port}/")


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/",
        "http://localhost:80/admin",
        "http://app.localhost/",
        "http://db.internal/",
        "http://printer.local/",
        "http://wiki.intranet/",
        "http://host.lan/",
        "http://metadata.google.internal/",
        "http://instance-data/",
    ],
)
def test_internal_hostnames_are_rejected(url: str) -> None:
    with pytest.raises(UnsafeUrlError):
        assert_url_is_safe(url)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://127.0.0.1:80/",
        "http://10.0.0.1/",
        "http://192.168.0.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
        "http://[::ffff:127.0.0.1]/",
    ],
)
def test_private_ip_literals_are_rejected(url: str) -> None:
    with pytest.raises(UnsafeUrlError):
        assert_url_is_safe(url)


def test_obfuscated_loopback_is_rejected() -> None:
    """Integer-encoded loopback.

    2130706433 == 127.0.0.1. Platforms differ on whether the resolver accepts
    the integer form at all; either outcome is a refusal, which is the property
    that matters.
    """
    with pytest.raises(UnsafeUrlError):
        assert_url_is_safe("http://2130706433/")


def test_empty_and_oversized_urls_are_rejected() -> None:
    with pytest.raises(UnsafeUrlError):
        assert_url_is_safe("")
    with pytest.raises(UnsafeUrlError):
        assert_url_is_safe("https://example.com/" + "a" * 3000)


def test_url_without_host_is_rejected() -> None:
    with pytest.raises(UnsafeUrlError):
        assert_url_is_safe("http:///just-a-path")


def test_error_message_does_not_leak_the_resolved_address() -> None:
    """The refusal must not become an internal-network oracle."""
    with pytest.raises(UnsafeUrlError) as caught:
        assert_url_is_safe("http://10.1.2.3/")
    assert "10.1.2.3" not in caught.value.reason


def test_a_hostname_resolving_to_a_private_address_is_rejected(monkeypatch) -> None:
    """The realistic attack: an attacker-controlled public name pointing inward."""

    def fake_getaddrinfo(host, *_args, **_kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("10.0.0.5", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(UnsafeUrlError, match="non-public"):
        assert_url_is_safe("https://evil.example.com/")


def test_rejected_when_any_resolved_address_is_private(monkeypatch) -> None:
    """One public A record must not launder a private one alongside it."""

    def fake_getaddrinfo(host, *_args, **_kwargs):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", 0)),
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("127.0.0.1", 0)),
        ]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(UnsafeUrlError, match="non-public"):
        assert_url_is_safe("https://mixed.example.com/")


def test_unresolvable_host_is_rejected(monkeypatch) -> None:
    def fake_getaddrinfo(*_args, **_kwargs):
        raise socket.gaierror("nope")

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(UnsafeUrlError, match="resolve"):
        assert_url_is_safe("https://does-not-exist.example/")


# --------------------------------------------------------------------------- #
# Fetching, including redirects
# --------------------------------------------------------------------------- #


@pytest.fixture
def public_dns(monkeypatch):
    """Resolve every hostname to a public address."""

    def fake_getaddrinfo(host, *_args, **_kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)


def test_successful_fetch_returns_extracted_body(public_dns) -> None:
    html = "<html><head><title>Acme</title></head><body><h1>Fleet software</h1></body></html>"
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, headers={"Content-Type": "text/html"}, text=html)
    )

    result = fetch_url("https://acme.example/", transport=transport)

    assert result.status_code == 200
    assert "Fleet software" in result.body
    assert result.content_type == "text/html"
    assert result.resolved_ips == ["93.184.216.34"]
    assert result.content_hash


def test_redirect_to_an_internal_address_is_blocked(public_dns, monkeypatch) -> None:
    """The control the HTTP client would otherwise bypass.

    A public URL that 302s to the metadata endpoint is the standard SSRF
    bypass. Redirects are followed manually so every hop is re-validated.
    """
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(302, headers={"Location": "http://169.254.169.254/latest/meta-data/"})

    transport = httpx.MockTransport(handler)

    with pytest.raises(UnsafeUrlError):
        fetch_url("https://acme.example/", transport=transport)

    # The first hop was made; the redirect target was never requested.
    assert calls == ["https://acme.example/"]


def test_relative_redirect_is_resolved_and_revalidated(public_dns) -> None:
    responses = [
        httpx.Response(301, headers={"Location": "/pricing"}),
        httpx.Response(200, headers={"Content-Type": "text/html"}, text="<p>Pricing</p>"),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return responses.pop(0)

    result = fetch_url("https://acme.example/", transport=httpx.MockTransport(handler))

    assert result.status_code == 200
    assert result.redirect_chain == ["https://acme.example/"]


def test_redirect_loop_is_capped(public_dns) -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(302, headers={"Location": "https://acme.example/next"})
    )

    with pytest.raises(FetchError, match="Too many redirects"):
        fetch_url("https://acme.example/", transport=transport, max_redirects=2)


def test_redirect_without_location_is_an_error(public_dns) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(302))

    with pytest.raises(FetchError, match="Location"):
        fetch_url("https://acme.example/", transport=transport)


def test_oversized_response_is_truncated_not_buffered(public_dns) -> None:
    """A multi-gigabyte response must not become a memory exhaustion bug."""
    body = "x" * 50_000
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, headers={"Content-Type": "text/html"}, text=body)
    )

    result = fetch_url("https://acme.example/", transport=transport, max_bytes=1024)

    assert result.truncated is True
    assert len(result.body) <= 1024


def test_understated_content_length_does_not_defeat_the_cap(public_dns) -> None:
    """The cap counts streamed bytes, so a lying Content-Length changes nothing."""
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers={"Content-Type": "text/html", "Content-Length": "10"},
            text="y" * 20_000,
        )
    )

    result = fetch_url("https://acme.example/", transport=transport, max_bytes=2048)

    assert len(result.body) <= 2048


@pytest.mark.parametrize(
    "content_type",
    ["application/pdf", "image/png", "application/zip", "application/octet-stream"],
)
def test_unsupported_content_types_are_refused(public_dns, content_type: str) -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, headers={"Content-Type": content_type}, content=b"...")
    )

    with pytest.raises(FetchError, match="content type"):
        fetch_url("https://acme.example/", transport=transport)


def test_timeout_is_reported_as_a_fetch_error(public_dns) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("too slow", request=request)

    with pytest.raises(FetchError, match="too long"):
        fetch_url("https://acme.example/", transport=httpx.MockTransport(handler))


def test_connection_failure_does_not_leak_internals(public_dns) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused to 10.0.0.1:443", request=request)

    with pytest.raises(FetchError) as caught:
        fetch_url("https://acme.example/", transport=httpx.MockTransport(handler))
    assert "10.0.0.1" not in str(caught.value)
