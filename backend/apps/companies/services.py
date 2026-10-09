"""Creating and merging company records.

Every path that produces a prospect -- a crawl, a file import, a provider, a
CRM sync -- comes through here, because deduplication that lives in the
importer is deduplication the next importer will not have.

The cost of getting this wrong is not a tidiness problem. Two rows for one
company means two leads, which means two campaigns, which means the same
person receives the same message twice from the same sender: the single most
reliable way to be reported as spam.
"""

from __future__ import annotations

from typing import Any

import structlog
from django.db import transaction
from django.utils import timezone

from apps.common.tenancy import tenant_context
from apps.companies.models import (
    Company,
    CompanyEvent,
    CompanyStatus,
    CompanyTechnology,
    normalise_domain,
)

logger = structlog.get_logger(__name__)

#: Fields a later, better-sourced observation may overwrite. Anything absent
#: is either immutable (the domain, which is the identity) or owned by a human
#: (status, the merge pointer).
ENRICHABLE_FIELDS = (
    "name",
    "legal_name",
    "website",
    "description",
    "industry",
    "sub_industry",
    "country",
    "city",
    "region",
    "employee_range",
    "revenue_range",
    "business_model",
    "founded_year",
    "phone",
    "linkedin_url",
)


@transaction.atomic
def upsert_company(
    *,
    organization: Any,
    source: str,
    domain: str = "",
    website: str = "",
    source_url: str = "",
    confidence: str = "medium",
    usage_license: str = "",
    **fields: Any,
) -> tuple[Company, bool]:
    """Create a company, or enrich the one already holding this domain.

    Returns ``(company, created)``.

    A domain belonging to a record that was merged away resolves to the
    survivor, so re-importing a list that names the old domain enriches the
    company it became rather than resurrecting the duplicate.

    A blank value never overwrites a populated one. A source that knows a
    company's name but not its city should not erase the city a previous
    source supplied, and importers routinely send empty strings for every
    column they do not have.
    """
    key = normalise_domain(domain or website)

    with tenant_context(organization=organization):
        existing = _resolve(organization=organization, domain=key) if key else None

        if existing is None:
            company = Company.objects.create(
                organization=organization,
                domain=key,
                website=website or fields.pop("website", ""),
                source=source,
                source_url=source_url,
                confidence=confidence,
                usage_license=usage_license,
                collected_at=timezone.now(),
                last_verified_at=timezone.now(),
                **{k: v for k, v in fields.items() if k in ENRICHABLE_FIELDS and v},
            )
            return company, True

        changed: list[str] = []
        for field in ENRICHABLE_FIELDS:
            value = fields.get(field)
            if not value or getattr(existing, field):
                continue
            setattr(existing, field, value)
            changed.append(field)

        # Re-seeing a company is itself information: it still exists, and the
        # freshness window should restart even when nothing new was learned.
        existing.last_verified_at = timezone.now()
        changed.append("last_verified_at")
        existing.save(update_fields=[*changed, "updated_at"])

        return existing, False


def _resolve(*, organization: Any, domain: str) -> Company | None:
    """Find the live company for a domain, following a merge if one happened.

    The uniqueness rule excludes merged rows, so a domain can legitimately be
    held by one duplicate and one active record at the same time; the active
    one wins, and a lone duplicate hands back whatever it was folded into.
    """
    matches = list(
        Company.objects.filter(organization=organization, domain=domain).select_related(
            "merged_into"
        )
    )
    if not matches:
        return None

    for company in matches:
        if company.status != CompanyStatus.DUPLICATE:
            return company

    return matches[0].merged_into


@transaction.atomic
def merge_companies(*, primary: Company, duplicate: Company) -> Company:
    """Fold one company into another, keeping the evidence of both.

    The duplicate is marked and pointed at the survivor rather than deleted:
    a lead, a conversation or a message may already reference it, and deleting
    the row would take that history with it. Section 61 also means the
    duplicate's provenance is worth keeping -- it records a place this company
    was found.
    """
    if primary.pk == duplicate.pk:
        return primary
    if primary.organization_id != duplicate.organization_id:
        raise ValueError("Refusing to merge companies belonging to different organizations.")

    with tenant_context(organization=primary.organization):
        for field in ENRICHABLE_FIELDS:
            if not getattr(primary, field) and getattr(duplicate, field):
                setattr(primary, field, getattr(duplicate, field))
        primary.save()

        duplicate.people.update(company=primary)
        duplicate.leads.update(company=primary)
        CompanyTechnology.objects.filter(company=duplicate).exclude(
            name__in=CompanyTechnology.objects.filter(company=primary).values("name")
        ).update(company=primary)
        CompanyEvent.objects.filter(company=duplicate).update(company=primary)

        # The duplicate keeps its domain: it is evidence of where this company
        # was found, and the uniqueness rule excludes merged rows rather than
        # requiring the record to be hollowed out to satisfy an index.
        duplicate.status = CompanyStatus.DUPLICATE
        duplicate.merged_into = primary
        duplicate.save(update_fields=["status", "merged_into", "updated_at"])

    logger.info(
        "companies_merged",
        organization_id=str(primary.organization.public_id),
        primary=str(primary.public_id),
        duplicate=str(duplicate.public_id),
    )
    return primary


@transaction.atomic
def record_technology(
    *, company: Company, name: str, source: str, category: str = "", **provenance: Any
) -> CompanyTechnology:
    """Note a technology in use, or confirm one already recorded.

    ``last_seen`` moving is the point: a technology that stops being seen is a
    change, and section 33 counts a technology change as a buying signal.
    """
    now = timezone.now()

    with tenant_context(organization=company.organization):
        technology, created = CompanyTechnology.objects.get_or_create(
            company=company,
            name=name,
            defaults={
                "organization": company.organization,
                "category": category,
                "source": source,
                "first_seen": now,
                "last_seen": now,
                "collected_at": now,
                "last_verified_at": now,
                **provenance,
            },
        )
        if not created:
            technology.last_seen = now
            technology.last_verified_at = now
            technology.is_current = True
            technology.save(
                update_fields=["last_seen", "last_verified_at", "is_current", "updated_at"]
            )
        return technology


__all__ = [
    "ENRICHABLE_FIELDS",
    "merge_companies",
    "record_technology",
    "upsert_company",
]
