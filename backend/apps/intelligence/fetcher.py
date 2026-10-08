"""SSRF-hardened HTTP fetcher (PRD section 109).

Every outbound fetch driven by user input goes through here. The platform takes
a URL from a customer and fetches it server side, which is textbook SSRF: a
naive implementation hands an attacker the ability to read the cloud metadata
endpoint, reach internal admin panels, and port-scan the private network from
inside it.

Controls, in order of application:

1. Scheme allowlist -- ``http`` and ``https`` only, so ``file://``,
   ``gopher://`` and ``dict://`` are out.
2. No credentials in the URL, which some clients forward to internal hosts.
3. Port allowlist -- 80 and 443, which stops the whole class of internal
   service probing on other ports.
4. Hostname denylist for names that resolve internally by convention.
5. DNS resolution, then every resolved address must be globally routable.
   This is what blocks 127.0.0.1, 10/8, 192.168/16, 169.254.169.254 (cloud
   metadata), IPv6 loopback and IPv4-mapped IPv6 forms of all of them.
6. Redirects followed manually, re-validating from step 1 at every hop. The
   HTTP client's own redirect handling is disabled, because a public URL that
   302s to 169.254.169.254 would otherwise sail straight through.
7. Response-size cap enforced while streaming, a hard timeout, and a
   content-type allowlist.

**Known residual risk: DNS rebinding.** Validation resolves the name, then the
client resolves it again when it connects. A name whose TTL expires between
those two moments could return a public address to us and a private one to the
connection. Closing that completely requires pinning the connection to the
validated IP while keeping TLS SNI on the original hostname. The production
mitigation is a network-level egress allowlist on the crawl worker, which is
why ``infra`` runs crawling on its own queue. Do not treat this module as
sufficient on its own in an environment with sensitive internal services.
"""

from __future__ import annotations

import hashlib
import ipaddress
import socket
import time
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit

import httpx
import structlog

logger = structlog.get_logger(__name__)

ALLOWED_SCHEMES = frozenset({"http", "https"})
ALLOWED_PORTS = frozenset({80, 443})
DEFAULT_PORTS = {"http": 80, "https": 443}

MAX_REDIRECTS = 3
DEFAULT_TIMEOUT_SECONDS = 10.0
MAX_RESPONSE_BYTES = 5 * 1024 * 1024

ALLOWED_CONTENT_TYPES = (
    "text/html",
    "application/xhtml+xml",
    "text/plain",
    "application/json",
    "text/xml",
    "application/xml",
)

USER_AGENT = "BridggaBot/0.1 (+https://bridgga.example/bot)"

# Names that conventionally resolve to infrastructure. DNS checks catch most of
# this, but an internal resolver can map these to public-looking addresses.
DENIED_HOSTNAMES = frozenset(
    {
        "localhost",
        "metadata",
        "metadata.google.internal",
        "instance-data",
        "169.254.169.254",
    }
)
DENIED_HOST_SUFFIXES = (
    ".localhost",
    ".local",
    ".internal",
    ".intranet",
    ".lan",
    ".home.arpa",
)


class UnsafeUrlError(ValueError):
    """The URL is refused before any connection is attempted."""

    def __init__(self, reason: str, url: str = "") -> None:
        super().__init__(reason)
        self.reason = reason
        self.url = url


class FetchError(RuntimeError):
    """The URL was permitted but could not be retrieved."""


@dataclass(slots=True)
class FetchResult:
    requested_url: str
    final_url: str
    status_code: int
    content_type: str
    body: str
    elapsed_ms: float
    redirect_chain: list[str] = field(default_factory=list)
    resolved_ips: list[str] = field(default_factory=list)
    truncated: bool = False

    @property
    def content_hash(self) -> str:
        """Stable digest, so an unchanged page is not re-analysed or re-billed."""
        return hashlib.sha256(self.body.encode("utf-8", "replace")).hexdigest()


def _is_public_address(raw_ip: str) -> bool:
    """True only for a globally routable address.

    ``is_global`` already excludes private, loopback, link-local, multicast,
    reserved and shared (100.64/10) ranges. The remaining checks are redundant
    on purpose: this is the single control standing between a customer-supplied
    hostname and the internal network.
    """
    try:
        address = ipaddress.ip_address(raw_ip)
    except ValueError:
        return False

    # ::ffff:127.0.0.1 is loopback wearing an IPv6 costume.
    mapped = getattr(address, "ipv4_mapped", None)
    if mapped is not None:
        address = mapped

    if (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    ):
        return False

    return bool(address.is_global)


def _resolve_host(hostname: str) -> list[str]:
    try:
        records = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UnsafeUrlError(f"Could not resolve host: {hostname}") from exc

    addresses = sorted({record[4][0] for record in records})
    if not addresses:
        raise UnsafeUrlError(f"Host resolved to no addresses: {hostname}")
    return addresses


def assert_url_is_safe(url: str) -> list[str]:
    """Validate a URL and return its resolved addresses.

    Raises :class:`UnsafeUrlError` with a reason safe to show a user; the
    reason never includes internal network detail beyond what they supplied.
    """
    if not url or len(url) > 2048:
        raise UnsafeUrlError("URL is empty or unreasonably long", url)

    parts = urlsplit(url.strip())

    if parts.scheme.lower() not in ALLOWED_SCHEMES:
        raise UnsafeUrlError("Only http and https URLs are supported", url)

    if parts.username or parts.password:
        raise UnsafeUrlError("URLs must not contain credentials", url)

    hostname = (parts.hostname or "").lower().rstrip(".")
    if not hostname:
        raise UnsafeUrlError("URL has no host", url)

    try:
        port = parts.port or DEFAULT_PORTS[parts.scheme.lower()]
    except ValueError as exc:
        raise UnsafeUrlError("URL has an invalid port", url) from exc

    if port not in ALLOWED_PORTS:
        raise UnsafeUrlError("Only ports 80 and 443 are supported", url)

    if hostname in DENIED_HOSTNAMES or hostname.endswith(DENIED_HOST_SUFFIXES):
        raise UnsafeUrlError("That host is not permitted", url)

    addresses = _resolve_host(hostname)
    for address in addresses:
        if not _is_public_address(address):
            # Deliberately does not echo the address back: that would turn the
            # error message into an internal-network oracle.
            raise UnsafeUrlError("That host resolves to a non-public address", url)

    return addresses


def fetch_url(
    url: str,
    *,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    max_bytes: int = MAX_RESPONSE_BYTES,
    max_redirects: int = MAX_REDIRECTS,
    transport: httpx.BaseTransport | None = None,
) -> FetchResult:
    """Fetch a customer-supplied URL under every control in this module.

    ``transport`` exists so tests can drive redirect chains, oversized bodies
    and hostile content types without a network. It is never set in
    production code.
    """
    started = time.monotonic()
    current_url = url.strip()
    redirect_chain: list[str] = []
    resolved_ips: list[str] = []

    # trust_env=False: proxy settings from the environment would route around
    # the address checks performed here.
    client = httpx.Client(
        follow_redirects=False,
        timeout=httpx.Timeout(timeout, connect=min(timeout, 5.0)),
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*;q=0.8"},
        trust_env=False,
        verify=True,
        transport=transport,
    )

    try:
        for hop in range(max_redirects + 1):
            resolved_ips = assert_url_is_safe(current_url)

            try:
                with client.stream("GET", current_url) as response:
                    if response.is_redirect:
                        location = response.headers.get("Location", "")
                        if not location:
                            raise FetchError("Redirect response had no Location header")
                        if hop >= max_redirects:
                            raise FetchError("Too many redirects")
                        redirect_chain.append(current_url)
                        # Relative redirects resolve against the current URL,
                        # then go back through validation on the next pass.
                        current_url = urljoin(current_url, location)
                        continue

                    content_type = (
                        response.headers.get("Content-Type", "").split(";")[0].strip().lower()
                    )
                    if content_type and not content_type.startswith(ALLOWED_CONTENT_TYPES):
                        raise FetchError(f"Unsupported content type: {content_type}")

                    # Trust the streamed byte count, not Content-Length, which
                    # a hostile server can understate.
                    chunks: list[bytes] = []
                    total = 0
                    truncated = False
                    for chunk in response.iter_bytes():
                        chunks.append(chunk)
                        total += len(chunk)
                        if total >= max_bytes:
                            truncated = True
                            break

                    raw = b"".join(chunks)[:max_bytes]
                    body = raw.decode(response.encoding or "utf-8", errors="replace")

                    return FetchResult(
                        requested_url=url,
                        final_url=str(response.url),
                        status_code=response.status_code,
                        content_type=content_type,
                        body=body,
                        elapsed_ms=round((time.monotonic() - started) * 1000, 2),
                        redirect_chain=redirect_chain,
                        resolved_ips=resolved_ips,
                        truncated=truncated,
                    )
            except httpx.TimeoutException as exc:
                raise FetchError("The site took too long to respond") from exc
            except httpx.HTTPError as exc:
                raise FetchError(f"Could not reach the site: {type(exc).__name__}") from exc

        raise FetchError("Too many redirects")
    finally:
        client.close()
