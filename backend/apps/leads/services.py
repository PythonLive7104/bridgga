"""Creating leads from discovered companies."""

from __future__ import annotations

from typing import Any

import structlog
from django.db import transaction
from django.utils import timezone

from apps.common.tenancy import tenant_context
from apps.leads.models import Lead, LeadSource, LeadStatus, SourceKind

logger = structlog.get_logger(__name__)


@transaction.atomic
def get_or_create_source(
    *, organization: Any, name: str, kind: str = SourceKind.MANUAL, **fields: Any
) -> LeadSource:
    with tenant_context(organization=organization):
        source, _ = LeadSource.objects.get_or_create(
            organization=organization,
            name=name,
            defaults={"kind": kind, **fields},
        )
        return source


@transaction.atomic
def create_lead(
    *,
    organization: Any,
    company: Any,
    source: LeadSource,
    icp: Any = None,
    person: Any = None,
    **fields: Any,
) -> tuple[Lead, bool]:
    """Register interest in a company, once per ICP.

    Returns ``(lead, created)``. Re-running discovery is expected to find the
    same companies again, so a second attempt updates the existing lead rather
    than raising -- and never resets a status somebody has moved on, because
    discovery is not entitled to undo a qualification or a disqualification.
    """
    with tenant_context(organization=organization):
        lead, created = Lead.objects.get_or_create(
            organization=organization,
            company=company,
            icp=icp,
            defaults={
                "source": source,
                "person": person,
                "first_seen_at": timezone.now(),
                **fields,
            },
        )

        if not created:
            updates: list[str] = []
            # Fill a contact in only where there was none: discovery finding a
            # second person is not grounds for replacing the one a rep chose.
            if person and lead.person_id is None:
                lead.person = person
                updates.append("person")
            if updates:
                lead.save(update_fields=[*updates, "updated_at"])

        return lead, created


@transaction.atomic
def disqualify(*, lead: Lead, reason: str) -> Lead:
    """Take a lead out of consideration, with the reason recorded.

    Not a delete. The fact that a company was looked at and rejected is worth
    keeping: without it, the next discovery run surfaces it again and somebody
    spends the same half hour reaching the same conclusion.
    """
    with tenant_context(organization=lead.organization):
        lead.status = LeadStatus.DISQUALIFIED
        lead.disqualified_reason = reason[:255]
        lead.save(update_fields=["status", "disqualified_reason", "updated_at"])
    return lead


__all__ = ["create_lead", "disqualify", "get_or_create_source"]
