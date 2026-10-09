"""Turning parsed rows into companies, people and leads (PRD section 51).

The order is deduplicate, validate, enrich, score, and it is the order for a
reason: validating before deduplicating means validating the same company
forty times, and enriching before deduplicating means paying for it forty
times too.

Every row goes through the same services the rest of the platform uses
(``companies.services.upsert_company``, ``contacts.services.upsert_person``).
An importer with its own insert logic is an importer that will deduplicate
differently from everything else, and the two will disagree quietly.
"""

from __future__ import annotations

from typing import Any

import structlog
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone

from apps.common.tenancy import tenant_context
from apps.companies import services as company_services
from apps.companies.models import normalise_domain
from apps.contacts import services as contact_services
from apps.leads import services as lead_services
from apps.leads.import_models import ImportJob, ImportStatus
from apps.leads.importing import ImportFileError, open_file

logger = structlog.get_logger(__name__)


class RowSkipped(Exception):
    """The row holds nothing usable. Counted, not reported as a failure."""


def clean_row(row: dict[str, Any], mapping: dict[str, str]) -> dict[str, str]:
    """Pull the mapped columns out of a raw row, trimmed."""
    cleaned: dict[str, str] = {}
    for field, header in mapping.items():
        value = row.get(header)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            cleaned[field] = text
    return cleaned


def validate_row(values: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    """Check what a row claims, returning the usable part and what was dropped.

    Dropping a bad field rather than rejecting the row is deliberate. A list
    where one person's address is malformed should still import that company
    and everyone else at it; refusing the row throws away good data because of
    a typo in a column the customer may not even have needed.
    """
    notes: list[str] = []
    cleaned = dict(values)

    email = cleaned.get("email", "").lower()
    if email:
        try:
            validate_email(email)
            cleaned["email"] = email
        except ValidationError:
            notes.append(f"Dropped unusable email address: {email[:80]}")
            cleaned.pop("email")

    country = cleaned.get("country", "")
    if country:
        # ISO alpha-2 is what the data model stores and what every country
        # filter compares against. A full name is common in exports, so it is
        # translated rather than rejected.
        code = _country_code(country)
        if code:
            cleaned["country"] = code
        else:
            notes.append(f"Unrecognised country: {country[:60]}")
            cleaned.pop("country")

    website = cleaned.get("website", "")
    if website and not normalise_domain(website):
        notes.append(f"Unusable website: {website[:80]}")
        cleaned.pop("website")

    # A row needs *something* to identify a company by, or there is nothing to
    # deduplicate on and every row becomes a new record.
    if not (cleaned.get("company") or cleaned.get("website") or cleaned.get("email")):
        raise RowSkipped("No company, website or email address.")

    return cleaned, notes


def _country_code(value: str) -> str:
    """Accept either an alpha-2 code or a country name we have seeded."""
    from apps.intelligence.models import CountryProfile

    candidate = value.strip()
    if len(candidate) == 2 and candidate.isalpha():
        return candidate.upper()

    match = CountryProfile.objects.filter(name__iexact=candidate).first()
    return match.code if match else ""


def _company_name(values: dict[str, str]) -> str:
    """Fall back to the domain when the file names no company.

    "acme.com" is a far more useful label than a blank, and it is what the
    customer will recognise in a prospect list.
    """
    if values.get("company"):
        return values["company"]
    domain = normalise_domain(values.get("website", ""))
    if domain:
        return domain
    return values.get("email", "").split("@")[-1]


def _split_name(values: dict[str, str]) -> dict[str, str]:
    """Derive first/last from a single name column, where that is all there is.

    A naive split, and knowingly so: it is right for most Western-ordered
    names and wrong for some. The full name is always stored verbatim, so
    nothing is lost -- these two fields are a convenience for personalisation
    and the original is what gets displayed.
    """
    if values.get("first_name") or values.get("last_name"):
        return {}
    full = values.get("full_name", "").strip()
    if not full or " " not in full:
        return {}
    first, _, last = full.partition(" ")
    return {"first_name": first, "last_name": last.strip()}


@transaction.atomic
def import_row(*, job: ImportJob, values: dict[str, str]) -> None:
    """Deduplicate, store and link one row's company, person and lead."""
    organization = job.organization
    source_label = f"import:{job.source.name}"[:100]

    company, created = company_services.upsert_company(
        organization=organization,
        source=source_label,
        website=values.get("website", ""),
        usage_license=job.source.usage_license,
        name=_company_name(values),
        industry=values.get("industry", ""),
        country=values.get("country", ""),
        city=values.get("city", ""),
        employee_range=values.get("employee_range", ""),
    )
    job.companies_created += created
    job.companies_updated += not created

    person = None
    if values.get("email") or values.get("full_name"):
        person, person_created = contact_services.upsert_person(
            organization=organization,
            company=company,
            email=values.get("email", ""),
            source=source_label,
            usage_license=job.source.usage_license,
            full_name=values.get("full_name", ""),
            job_title=values.get("job_title", ""),
            phone=values.get("phone", ""),
            linkedin_url=values.get("linkedin_url", ""),
            country=values.get("country", ""),
            city=values.get("city", ""),
            **_split_name(values),
        )
        job.people_created += person_created
        job.people_updated += not person_created

    _, lead_created = lead_services.create_lead(
        organization=organization,
        company=company,
        source=job.source,
        icp=job.icp,
        person=person,
    )
    job.leads_created += lead_created


def run_import(*, job: ImportJob) -> ImportJob:
    """Process an entire file, recording the fate of every row.

    Row failures are counted and reported; they never stop the run. A list of
    four thousand prospects with nine bad rows should import three thousand
    nine hundred and ninety-one of them.
    """
    with tenant_context(organization=job.organization):
        job.status = ImportStatus.RUNNING
        job.started_at = timezone.now()
        job.errors = []
        job.save(update_fields=["status", "started_at", "errors", "updated_at"])

    mapping = job.column_mapping or {}
    if not mapping:
        return _fail(job, "No column mapping was set for this import.")

    try:
        with job.file.open("rb") as stream:
            _, rows = open_file(stream, filename=job.original_filename)

            for number, row in enumerate(rows, start=2):  # row 1 is the header
                if number - 1 > settings.IMPORT_MAX_ROWS:
                    job.record_error(
                        row=number,
                        message=f"Stopped at the {settings.IMPORT_MAX_ROWS:,} row limit.",
                    )
                    break

                job.total_rows += 1
                try:
                    values, notes = validate_row(clean_row(row, mapping))
                    for note in notes:
                        job.record_error(row=number, message=note)
                        # A dropped field is not a failed row.
                        job.rows_failed -= 1
                    import_row(job=job, values=values)
                except RowSkipped as exc:
                    job.rows_skipped += 1
                    logger.debug("import_row_skipped", row=number, reason=str(exc))
                except Exception as exc:  # one bad row must not end the run
                    job.record_error(row=number, message=str(exc))
                    logger.warning("import_row_failed", row=number, error=str(exc)[:200])

    except ImportFileError as exc:
        return _fail(job, str(exc))
    except Exception as exc:
        logger.exception("import_failed", job_id=str(job.public_id))
        return _fail(job, f"The file could not be processed: {exc}")

    with tenant_context(organization=job.organization):
        job.status = ImportStatus.PARTIAL if job.rows_failed else ImportStatus.COMPLETED
        job.finished_at = timezone.now()
        job.save()

    logger.info(
        "import_complete",
        organization_id=str(job.organization.public_id),
        job_id=str(job.public_id),
        **job.summary(),
    )
    return job


def _fail(job: ImportJob, reason: str) -> ImportJob:
    with tenant_context(organization=job.organization):
        job.status = ImportStatus.FAILED
        job.error_message = reason[:500]
        job.finished_at = timezone.now()
        job.save()
    return job


__all__ = ["RowSkipped", "clean_row", "import_row", "run_import", "validate_row"]
