"""Website analysis records.

A ``WebsiteSnapshot`` is the raw evidence behind everything the AI later claims
about a company. PRD section 58 requires that when the system says "this
company recently expanded", it can still produce the source, the URL and the
retrieval time. That is only possible if the fetch is stored as a first-class
record rather than used and discarded, so snapshots are kept and referenced
rather than overwritten.
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import TenantOwnedModel


class SnapshotStatus(models.TextChoices):
    PENDING = "pending", _("Pending")
    OK = "ok", _("Fetched")
    REFUSED = "refused", _("Refused as unsafe")
    FAILED = "failed", _("Fetch failed")


class WebsiteSnapshot(TenantOwnedModel):
    """One fetch of one URL, with what was extracted from it."""

    requested_url = models.URLField(_("requested URL"), max_length=2048)
    final_url = models.URLField(_("final URL"), max_length=2048, blank=True)

    status = models.CharField(
        _("status"), max_length=16, choices=SnapshotStatus.choices, default=SnapshotStatus.PENDING
    )
    status_code = models.PositiveSmallIntegerField(_("HTTP status"), null=True, blank=True)
    content_type = models.CharField(_("content type"), max_length=100, blank=True)

    # Why a fetch was refused or failed, in words safe to show the user.
    error_reason = models.CharField(_("error reason"), max_length=255, blank=True)

    title = models.CharField(_("title"), max_length=300, blank=True)
    description = models.TextField(_("meta description"), blank=True)
    language = models.CharField(_("language"), max_length=10, blank=True)
    canonical_url = models.URLField(_("canonical URL"), max_length=2048, blank=True)

    headings = models.JSONField(_("headings"), default=list, blank=True)
    text = models.TextField(_("extracted text"), blank=True)
    internal_links = models.JSONField(_("internal links"), default=list, blank=True)
    social_links = models.JSONField(_("social links"), default=list, blank=True)
    emails = models.JSONField(_("public emails"), default=list, blank=True)

    # Provenance (PRD section 61). resolved_ips is kept for incident review:
    # if a crawl ever reaches somewhere it should not, this is the audit trail.
    content_hash = models.CharField(_("content hash"), max_length=64, blank=True, db_index=True)
    resolved_ips = models.JSONField(_("resolved IPs"), default=list, blank=True)
    truncated = models.BooleanField(_("truncated"), default=False)
    elapsed_ms = models.FloatField(_("elapsed ms"), null=True, blank=True)
    fetched_at = models.DateTimeField(_("fetched at"), null=True, blank=True, db_index=True)

    class Meta:
        verbose_name = _("website snapshot")
        verbose_name_plural = _("website snapshots")
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(
                fields=["organization", "requested_url", "-created_at"],
                name="snapshot_org_url_idx",
            ),
            models.Index(fields=["organization", "status"], name="snapshot_org_status_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.requested_url} ({self.status})"

    @property
    def succeeded(self) -> bool:
        return self.status == SnapshotStatus.OK

    def summary_for_prompt(self, *, max_chars: int = 12_000) -> str:
        """Compact representation for an AI prompt.

        Returned text is **untrusted page content**. Callers must place it in a
        data section of a prompt and never concatenate it into instructions.
        """
        parts = [
            f"URL: {self.final_url or self.requested_url}",
            f"Title: {self.title}" if self.title else "",
            f"Description: {self.description}" if self.description else "",
            "Headings: " + " | ".join(self.headings[:20]) if self.headings else "",
            "",
            self.text,
        ]
        return "\n".join(part for part in parts if part)[:max_chars]
