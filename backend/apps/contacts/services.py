"""Creating and updating people.

Separate from the company services because the rules are different in one
important way: a contact's quality statuses are not enrichable. A later source
claiming an address is fine does not undo a bounce, and an opt-out is never
overwritten by anything.
"""

from __future__ import annotations

from typing import Any

import structlog
from django.db import transaction
from django.utils import timezone

from apps.common.models import UNSENDABLE_CONTACT_STATUSES, ContactStatus
from apps.common.tenancy import tenant_context
from apps.contacts.models import Person

logger = structlog.get_logger(__name__)

#: Fields a later source may *fill in* but never overwrite. First writer
#: wins, because a provider is not entitled to correct what the customer or an
#: earlier, better source already recorded.
ENRICHABLE_FIELDS = (
    "first_name",
    "last_name",
    "full_name",
    "job_title",
    "department",
    "seniority",
    "linkedin_url",
    "country",
    "city",
    "phone",
)

#: Handled separately from ENRICHABLE_FIELDS because "first writer wins" does
#: not work for a boolean: False and "not stated" are the same value, so an
#: unset flag would block a later source that knows better. It is promoted to
#: True and never demoted -- the same asymmetry as email status, and for the
#: same reason. A provider saying "not a decision maker" is not grounds to
#: discard a judgement somebody here already made.
PROMOTABLE_FLAGS = ("is_decision_maker",)

_ACCEPTED_FIELDS = frozenset(ENRICHABLE_FIELDS) | frozenset(PROMOTABLE_FLAGS)


@transaction.atomic
def upsert_person(
    *,
    organization: Any,
    company: Any,
    email: str = "",
    source: str = "",
    source_url: str = "",
    confidence: str = "medium",
    usage_license: str = "",
    email_status: str = "",
    **fields: Any,
) -> tuple[Person, bool]:
    """Create a person, or enrich the one already holding this address.

    Returns ``(person, created)``.

    An unrecognised keyword raises rather than being dropped. The permissive
    version silently discarded anything not on the enrichable list, so a
    caller passing a real field by a slightly wrong name -- or a real field
    that had simply never been added to the list -- got no error and no
    effect, and the gap only surfaced when somebody noticed the data missing
    much later.

    An existing record's ``email_status`` is left alone unless the incoming
    one is *worse*. A provider asserting "verified" must never clear a bounce
    or an unsubscribe: the first is a fact we observed ourselves and they did
    not, and the second is a compliance obligation under section 63 that no
    third party is in a position to lift.
    """
    unexpected = sorted(set(fields) - _ACCEPTED_FIELDS)
    if unexpected:
        raise TypeError(
            f"upsert_person() got unexpected field(s): {', '.join(unexpected)}. "
            f"Accepted: {', '.join(sorted(_ACCEPTED_FIELDS))}."
        )

    address = (email or "").strip().lower()

    with tenant_context(organization=organization):
        existing = (
            Person.objects.filter(organization=organization, email=address).first()
            if address
            else None
        )

        if existing is None:
            person = Person.objects.create(
                organization=organization,
                company=company,
                email=address,
                email_status=email_status or ContactStatus.UNKNOWN,
                email_source=source,
                source=source,
                source_url=source_url,
                confidence=confidence,
                usage_license=usage_license,
                collected_at=timezone.now(),
                last_verified_at=timezone.now(),
                last_seen_at=timezone.now(),
                **{k: v for k, v in fields.items() if k in _ACCEPTED_FIELDS and v},
            )
            return person, True

        changed: list[str] = []
        for field in ENRICHABLE_FIELDS:
            value = fields.get(field)
            if not value or getattr(existing, field):
                continue
            setattr(existing, field, value)
            changed.append(field)

        for flag in PROMOTABLE_FLAGS:
            if fields.get(flag) and not getattr(existing, flag):
                setattr(existing, flag, True)
                changed.append(flag)

        if email_status and _is_downgrade(existing.email_status, email_status):
            existing.email_status = email_status
            existing.email_verified_at = timezone.now()
            changed += ["email_status", "email_verified_at"]

        existing.last_seen_at = timezone.now()
        existing.last_verified_at = timezone.now()
        changed += ["last_seen_at", "last_verified_at"]
        existing.save(update_fields=[*changed, "updated_at"])

        return existing, False


def _is_downgrade(current: str, incoming: str) -> bool:
    """Whether an incoming status is worse than the one already recorded.

    Only a downgrade is applied automatically. Deliverability is something the
    platform learns the hard way -- from a bounce, or from someone asking to be
    left alone -- and a cheerful "verified" from a data vendor is not evidence
    against either.
    """
    if current in UNSENDABLE_CONTACT_STATUSES:
        return False
    return incoming in UNSENDABLE_CONTACT_STATUSES or (
        current == ContactStatus.UNKNOWN and incoming == ContactStatus.RISKY
    )


@transaction.atomic
def mark_verified(*, person: Person, source: str = "") -> Person:
    """Record that an address was checked and looks deliverable.

    Refuses on a record that bounced or opted out, rather than quietly doing
    nothing: a caller trying to re-verify one of those has misunderstood
    something, and the exception is where they find out.
    """
    if person.email_status in UNSENDABLE_CONTACT_STATUSES:
        raise ValueError(
            f"Refusing to mark {person.email_status} address as verified; "
            "a bounce or an opt-out is not reversible by verification."
        )

    with tenant_context(organization=person.organization):
        person.email_status = ContactStatus.VERIFIED
        person.email_verified_at = timezone.now()
        if source:
            person.email_source = source
        person.save(
            update_fields=["email_status", "email_verified_at", "email_source", "updated_at"]
        )
    return person


__all__ = ["ENRICHABLE_FIELDS", "PROMOTABLE_FLAGS", "mark_verified", "upsert_person"]
