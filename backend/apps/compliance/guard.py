"""The check no send may skip (PRD section 63).

Every outbound message to a prospect passes through ``assert_sendable`` or
``partition``. Not "should": there is a test that fails the build if any module
outside the delivery layer constructs an outbound message, and this is the
only thing the delivery layer may call to decide who receives one.

**Why a function and not a database constraint.** "This address is not on the
suppression list" cannot be expressed as a constraint, and a signal on message
creation would fire after the decision was made. What can be enforced
structurally is the *shape*: one entry point, one place to audit, and an
architecture test that keeps every other path closed.

**It fails closed.** An unreadable address, a missing organization, a
suppression query that errors -- all of them block the send. The cost of
blocking a legitimate message is an unsent email. The cost of sending a
blocked one is a person who asked to be left alone being contacted anyway,
which section 63 treats as a compliance failure rather than a bug.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog

from apps.compliance.models import (
    SuppressionEntry,
    SuppressionKind,
    SuppressionScope,
    address_hash,
    domain_of,
    normalise_address,
)

logger = structlog.get_logger(__name__)


class Suppressed(Exception):
    """This recipient must not be contacted.

    Carries the reason so the caller can record *why* a message was not sent,
    which is what makes a campaign report honest rather than merely shorter.
    """

    def __init__(self, address: str, reason: str, scope: str = "", kind: str = "") -> None:
        super().__init__(f"{address or 'recipient'} is suppressed ({reason})")
        self.address = address
        self.reason = reason
        self.scope = scope
        self.kind = kind


@dataclass(slots=True)
class Blocked:
    address: str
    reason: str
    kind: str = ""


def _scopes_for(channel: str) -> list[str]:
    """A channel is covered by its own scope and by an all-channel entry."""
    channel = (channel or SuppressionScope.EMAIL).lower()
    return [SuppressionScope.ALL, channel]


def suppression_for(
    *, organization: Any, address: str, channel: str = SuppressionScope.EMAIL
) -> SuppressionEntry | None:
    """The entry blocking this address, or None.

    Matches the address itself and the domain it belongs to, because a company
    that asks to be left alone has asked on behalf of addresses nobody has
    discovered yet.
    """
    normalised = normalise_address(address)
    if not normalised:
        return None

    hashes = [address_hash(normalised)]
    kinds = [SuppressionKind.EMAIL, SuppressionKind.PHONE]

    domain = domain_of(normalised)
    if domain:
        hashes.append(address_hash(domain))
        kinds.append(SuppressionKind.DOMAIN)

    return (
        SuppressionEntry.all_objects.filter(
            organization_id=organization.pk,
            value_hash__in=hashes,
            kind__in=kinds,
            scope__in=_scopes_for(channel),
        )
        .order_by("suppressed_at")
        .first()
    )


def is_suppressed(
    *, organization: Any, address: str, channel: str = SuppressionScope.EMAIL
) -> bool:
    return suppression_for(organization=organization, address=address, channel=channel) is not None


def assert_sendable(
    *, organization: Any, address: str, channel: str = SuppressionScope.EMAIL, person: Any = None
) -> str:
    """Raise unless this address may be contacted. Returns the normalised form.

    The order of the checks is the order of their authority: an empty address
    is unusable, the person record's own status is a local fact, and the
    suppression list is the organization-wide decision that outlives any
    individual record.
    """
    normalised = normalise_address(address)
    if not normalised:
        raise Suppressed(address, "no address")

    if organization is None:
        # Fails closed: without a tenant there is no suppression list to check
        # against, and "we could not check" must never read as "it is fine".
        raise Suppressed(normalised, "no organization to check against")

    if (
        person is not None
        and not person.can_be_emailed
        and channel
        in {
            SuppressionScope.ALL,
            SuppressionScope.EMAIL,
        }
    ):
        raise Suppressed(normalised, f"contact status is {person.email_status}")

    entry = suppression_for(organization=organization, address=normalised, channel=channel)
    if entry is not None:
        raise Suppressed(normalised, entry.reason, scope=entry.scope, kind=entry.kind)

    return normalised


@dataclass(slots=True)
class Partition:
    """Who may be contacted, and who may not and why."""

    allowed: list[str]
    blocked: list[Blocked]

    @property
    def blocked_reasons(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in self.blocked:
            counts[item.reason] = counts.get(item.reason, 0) + 1
        return counts


def partition(
    *, organization: Any, addresses: list[str], channel: str = SuppressionScope.EMAIL
) -> Partition:
    """Split a recipient list in one query rather than one per address.

    The pre-launch panel in section 36 needs this before a campaign starts --
    "412 recipients, 37 suppressed" is a number a human approves against -- and
    the scheduler needs it again at send time, because the list can change
    between approval and delivery.
    """
    normalised = [normalise_address(address) for address in addresses]
    usable = [address for address in normalised if address]

    if organization is None:
        return Partition(
            allowed=[],
            blocked=[Blocked(address, "no organization to check against") for address in usable],
        )

    wanted: dict[str, list[str]] = {}
    for address in usable:
        wanted.setdefault(address_hash(address), []).append(address)
        domain = domain_of(address)
        if domain:
            wanted.setdefault(address_hash(domain), []).append(address)

    entries = SuppressionEntry.all_objects.filter(
        organization_id=organization.pk,
        value_hash__in=list(wanted),
        scope__in=_scopes_for(channel),
    ).values_list("value_hash", "reason", "kind")

    blocked_by_address: dict[str, Blocked] = {}
    for value_hash, reason, kind in entries:
        for address in wanted.get(value_hash, []):
            blocked_by_address.setdefault(address, Blocked(address, reason, kind))

    seen: set[str] = set()
    allowed: list[str] = []
    blocked: list[Blocked] = []
    for address in normalised:
        if not address:
            blocked.append(Blocked(address, "no address"))
            continue
        if address in seen:
            # A list containing the same address twice is one recipient, not
            # two. Sending both is how one person receives a campaign twice.
            continue
        seen.add(address)
        if address in blocked_by_address:
            blocked.append(blocked_by_address[address])
        else:
            allowed.append(address)

    if blocked:
        logger.info(
            "suppression_blocked",
            organization_id=str(organization.public_id),
            channel=channel,
            blocked=len(blocked),
            allowed=len(allowed),
        )
    return Partition(allowed=allowed, blocked=blocked)


__all__ = [
    "Blocked",
    "Partition",
    "Suppressed",
    "assert_sendable",
    "is_suppressed",
    "partition",
    "suppression_for",
]
