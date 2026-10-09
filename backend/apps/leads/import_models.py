"""Lead imports (PRD sections 51, 110).

An import is a long-running, partially-failing operation over a file somebody
uploaded, so it is a record rather than a request. Three things follow from
that and shape this model:

* **It must be resumable and inspectable.** A customer who uploads four
  thousand rows and gets "failed" has learned nothing. Counts are kept per
  outcome, and per-row errors are stored with their row numbers.
* **Partial success is the normal case.** Real prospect lists have blank
  rows, broken addresses and three spellings of the same company. A run that
  aborts on the first bad row is useless; one that silently drops them is
  worse.
* **The file is untrusted** (section 110): size-capped, type-checked, stored
  under a random name inside a tenant-scoped path, and never served back by
  the name the uploader chose.
"""

from __future__ import annotations

import uuid
from pathlib import PurePosixPath
from typing import Any

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import TenantOwnedModel


def import_upload_path(instance: ImportJob, filename: str) -> str:
    """Where an uploaded file is stored.

    The uploader's filename is never used: it is attacker-controlled, and a
    name like ``../../settings.py`` or one colliding with another tenant's
    upload is a problem the storage layer should never be asked to solve. The
    original is kept in a column, for display only.

    The path is tenant-scoped so that bucket-level access rules can be written
    per organization rather than per object.
    """
    suffix = PurePosixPath(filename).suffix.lower()[:10]
    return f"imports/{instance.organization.public_id}/{uuid.uuid4().hex}{suffix}"


class ImportStatus(models.TextChoices):
    PENDING = "pending", _("Uploaded, awaiting column mapping")
    READY = "ready", _("Mapped, ready to run")
    RUNNING = "running", _("Running")
    COMPLETED = "completed", _("Completed")
    #: Rows were imported, and some were not. Distinct from `completed`
    #: because "3,900 of 4,000" is a different thing to tell someone.
    PARTIAL = "partial", _("Completed with errors")
    FAILED = "failed", _("Failed")
    CANCELLED = "cancelled", _("Cancelled")


class ImportJob(TenantOwnedModel):
    """One uploaded file, and what became of every row in it."""

    #: Errors kept per job. Beyond this the file is wrong in a structural way
    #: and the next thousand messages say the same thing; the count still
    #: reflects every failure.
    MAX_STORED_ERRORS = 200

    file = models.FileField(_("file"), upload_to=import_upload_path, max_length=400)
    original_filename = models.CharField(_("original filename"), max_length=255)
    content_type = models.CharField(_("content type"), max_length=100, blank=True)
    size_bytes = models.PositiveBigIntegerField(_("size"), default=0)

    source = models.ForeignKey(
        "leads.LeadSource",
        on_delete=models.PROTECT,
        related_name="import_jobs",
        verbose_name=_("source"),
    )
    icp = models.ForeignKey(
        "intelligence.ICP",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="import_jobs",
        verbose_name=_("assign to ICP"),
    )

    status = models.CharField(
        _("status"), max_length=16, choices=ImportStatus.choices, default=ImportStatus.PENDING
    )

    # {canonical field: column header}. Suggested from the headers, then
    # confirmed by the customer -- guessing silently is how a phone column
    # ends up in the email field for four thousand people.
    column_mapping = models.JSONField(_("column mapping"), default=dict, blank=True)
    detected_headers = models.JSONField(_("detected headers"), default=list, blank=True)
    sample_rows = models.JSONField(_("sample rows"), default=list, blank=True)

    total_rows = models.PositiveIntegerField(_("rows"), default=0)
    companies_created = models.PositiveIntegerField(_("companies created"), default=0)
    companies_updated = models.PositiveIntegerField(_("companies updated"), default=0)
    people_created = models.PositiveIntegerField(_("people created"), default=0)
    people_updated = models.PositiveIntegerField(_("people updated"), default=0)
    leads_created = models.PositiveIntegerField(_("leads created"), default=0)
    rows_skipped = models.PositiveIntegerField(_("rows skipped"), default=0)
    rows_failed = models.PositiveIntegerField(_("rows failed"), default=0)

    errors = models.JSONField(_("errors"), default=list, blank=True)
    error_message = models.CharField(_("error"), max_length=500, blank=True)

    requested_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="import_jobs",
        verbose_name=_("requested by"),
    )
    started_at = models.DateTimeField(_("started at"), null=True, blank=True)
    finished_at = models.DateTimeField(_("finished at"), null=True, blank=True)

    class Meta:
        verbose_name = _("import job")
        verbose_name_plural = _("import jobs")
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["organization", "status"], name="import_org_status_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.original_filename} ({self.status})"

    @property
    def rows_processed(self) -> int:
        return self.leads_created + self.rows_skipped + self.rows_failed

    @property
    def is_finished(self) -> bool:
        return self.status in {
            ImportStatus.COMPLETED,
            ImportStatus.PARTIAL,
            ImportStatus.FAILED,
            ImportStatus.CANCELLED,
        }

    def record_error(self, *, row: int, message: str) -> None:
        """Note a row that could not be imported, without unbounded growth."""
        self.rows_failed += 1
        if len(self.errors) < self.MAX_STORED_ERRORS:
            self.errors.append({"row": row, "message": message[:300]})

    def summary(self) -> dict[str, Any]:
        return {
            "total_rows": self.total_rows,
            "companies_created": self.companies_created,
            "companies_updated": self.companies_updated,
            "people_created": self.people_created,
            "leads_created": self.leads_created,
            "rows_skipped": self.rows_skipped,
            "rows_failed": self.rows_failed,
        }
