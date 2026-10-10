"""Recording suppressions, consent and erasure (PRD sections 62 and 63).

``suppress`` is the only way an entry is created, because section 63 asks for
three things at once -- suppress immediately, prevent accidental
re-enrollment, record the timestamp -- and they have to happen together or the
gap between them is a message.

The re-enrollment half is the part that is easy to miss. The suppression list
is authoritative at send time, but a person left marked contactable will be
pulled into the next campaign's audience, counted in its estimate, and
rejected one at a time at the end. So suppressing also marks the matching
``Person`` records unsubscribed: one source of truth for *may we send*, and a
denormalised copy for *who should even be considered*.
"""

from __future__ import annotations

from typing import Any

import structlog
from django.db import transaction
from django.utils import timezone

from apps.common.models import ContactStatus
from apps.common.tenancy import tenant_context
from apps.compliance.models import (
    ConsentBasis,
    ConsentRecord,
    SuppressionEntry,
    SuppressionKind,
    SuppressionReason,
    SuppressionScope,
    address_hash,
    normalise_address,
)

logger = structlog.get_logger(__name__)


@transaction.atomic
def suppress(
    *,
    organization: Any,
    address: str,
    reason: str = SuppressionReason.UNSUBSCRIBED,
    scope: str = SuppressionScope.ALL,
    kind: str = SuppressionKind.EMAIL,
    source: str = "",
    person: Any = None,
    created_by: Any = None,
    evidence: dict[str, Any] | None = None,
    suppressed_at: Any = None,
    notes: str = "",
) -> SuppressionEntry:
    """Add somebody to the suppression list, and stop them being re-enrolled.

    Idempotent: unsubscribing twice is one entry, and the first timestamp is
    kept because it is the one that answers "when did they ask?".
    """
    normalised = normalise_address(address)
    if not normalised:
        raise ValueError("An address is required to suppress.")

    with tenant_context(organization=organization):
        entry, created = SuppressionEntry.objects.get_or_create(
            organization=organization,
            kind=kind,
            value_hash=address_hash(normalised),
            scope=scope,
            defaults={
                "value": normalised[:320],
                "reason": reason,
                "source": source,
                "person": person,
                "created_by": created_by if getattr(created_by, "pk", None) else None,
                "evidence": evidence or {},
                "suppressed_at": suppressed_at or timezone.now(),
                "notes": notes,
            },
        )

        if not created:
            # Already on the list. Record what else we learned without moving
            # the original date or softening the original reason: a person who
            # unsubscribed and later complained is still, first, somebody who
            # unsubscribed on the earlier date.
            changed: list[str] = []
            if person is not None and entry.person_id is None:
                entry.person = person
                changed.append("person")
            if evidence:
                entry.evidence = {**(entry.evidence or {}), **evidence}
                changed.append("evidence")
            if changed:
                entry.save(update_fields=[*changed, "updated_at"])

        _mark_people_unsubscribed(organization=organization, address=normalised, person=person)

    logger.info(
        "suppression_recorded",
        organization_id=str(organization.public_id),
        reason=reason,
        scope=scope,
        kind=kind,
        created=created,
        source=source,
    )
    return entry


def _mark_people_unsubscribed(*, organization: Any, address: str, person: Any = None) -> int:
    """Keep the contact records in step with the suppression list.

    Not the authority -- the list is -- but without this a suppressed person
    stays in every audience estimate and every prospect filter marked
    "reachable today", which is how a campaign is approved for 400 recipients
    and sends to 380 with no explanation.
    """
    from apps.contacts.models import Person

    queryset = Person.all_objects.filter(organization_id=organization.pk, email=address)
    updated = 0
    for record in queryset:
        if record.email_status != ContactStatus.UNSUBSCRIBED:
            record.email_status = ContactStatus.UNSUBSCRIBED
            record.save(update_fields=["email_status", "updated_at"])
            updated += 1

    if person is not None and person.email_status != ContactStatus.UNSUBSCRIBED:
        person.email_status = ContactStatus.UNSUBSCRIBED
        person.save(update_fields=["email_status", "updated_at"])
        updated += 1
    return updated


@transaction.atomic
def unsuppress(*, entry: SuppressionEntry, actor: Any = None) -> bool:
    """Remove an entry, if it is one that may be removed.

    Returns False for an unsubscribe, a complaint or an erasure request. Those
    record somebody's decision, and a button that deletes them has exactly one
    use: contacting a person who said stop. A mistyped manual entry is a
    different thing and can be corrected.
    """
    if not entry.is_removable:
        logger.warning(
            "suppression_removal_refused",
            organization_id=str(entry.organization.public_id),
            reason=entry.reason,
            actor=getattr(actor, "pk", None),
        )
        return False

    with tenant_context(organization=entry.organization):
        entry.delete()
    return True


@transaction.atomic
def erase(*, organization: Any, address: str, actor: Any = None) -> dict[str, int]:
    """Honour an erasure request without losing the ability to honour the opt-out.

    Section 63's closing requirement reads like a contradiction: delete the
    person, and keep what is needed to keep not contacting them. Hashing is
    what resolves it -- the plaintext goes, the hash stays, and the send path
    still recognises them.

    Suppression is recorded *first*, so an erasure never leaves a window in
    which the person is deleted but contactable.
    """
    from apps.contacts.models import Person

    normalised = normalise_address(address)
    entry = suppress(
        organization=organization,
        address=normalised,
        reason=SuppressionReason.LEGAL_REQUEST,
        source="erasure_request",
        created_by=actor,
    )

    with tenant_context(organization=organization):
        entry.value = ""
        entry.redacted_at = timezone.now()
        entry.save(update_fields=["value", "redacted_at", "updated_at"])

        ConsentRecord.objects.filter(
            organization=organization, value_hash=address_hash(normalised)
        ).update(value="", withdrawn_at=timezone.now())

        people = list(Person.all_objects.filter(organization_id=organization.pk, email=normalised))
        for person in people:
            person.email = ""
            person.first_name = ""
            person.last_name = ""
            person.full_name = ""
            person.phone = ""
            person.linkedin_url = ""
            person.email_status = ContactStatus.UNSUBSCRIBED
            person.metadata = {"erased_at": timezone.now().isoformat()}
            person.save()

    logger.info(
        "personal_data_erased",
        organization_id=str(organization.public_id),
        people=len(people),
    )
    return {"suppressed": 1, "people_redacted": len(people)}


@transaction.atomic
def record_consent(
    *,
    organization: Any,
    address: str,
    basis: str = ConsentBasis.LEGITIMATE_INTEREST,
    source: str = "",
    evidence: str = "",
    country: str = "",
    person: Any = None,
    captured_at: Any = None,
) -> ConsentRecord:
    """Record why this customer believes they may contact this person."""
    normalised = normalise_address(address)

    with tenant_context(organization=organization):
        return ConsentRecord.objects.create(
            organization=organization,
            person=person,
            value_hash=address_hash(normalised),
            value=normalised[:320],
            basis=basis,
            source=source,
            evidence=evidence,
            country=(country or "").upper()[:2],
            captured_at=captured_at or timezone.now(),
        )


def active_consent(*, organization: Any, address: str) -> ConsentRecord | None:
    return (
        ConsentRecord.all_objects.filter(
            organization_id=organization.pk,
            value_hash=address_hash(address),
            withdrawn_at__isnull=True,
        )
        .order_by("-captured_at")
        .first()
    )


def import_suppressions(
    *, organization: Any, addresses: list[str], source: str = "import", created_by: Any = None
) -> dict[str, int]:
    """Bring an existing suppression list across.

    The first thing a customer moving from another tool needs, and the thing
    most likely to be skipped in a hurry. Bad rows are counted rather than
    aborting the import: an address that cannot be parsed should not strand
    the nine hundred that can.
    """
    added = skipped = 0
    for address in addresses:
        try:
            suppress(
                organization=organization,
                address=address,
                reason=SuppressionReason.IMPORTED,
                source=source,
                created_by=created_by,
            )
            added += 1
        except ValueError:
            skipped += 1
    return {"added": added, "skipped": skipped}


__all__ = [
    "active_consent",
    "erase",
    "import_suppressions",
    "record_consent",
    "suppress",
    "unsuppress",
]
