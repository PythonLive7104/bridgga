"""Website analysis records.

A ``WebsiteSnapshot`` is the raw evidence behind everything the AI later claims
about a company. PRD section 58 requires that when the system says "this
company recently expanded", it can still produce the source, the URL and the
retrieval time. That is only possible if the fetch is stored as a first-class
record rather than used and discarded, so snapshots are kept and referenced
rather than overwritten.

``CompanyProfile`` is what the AI made of those snapshots, and is editable by
the customer -- see its docstring for how an edit survives re-analysis.
"""

from __future__ import annotations

from typing import Any

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


class ProfileStatus(models.TextChoices):
    DRAFT = "draft", _("Draft")
    ANALYZING = "analyzing", _("Analyzing")
    READY = "ready", _("Ready for review")
    CONFIRMED = "confirmed", _("Confirmed by the customer")
    FAILED = "failed", _("Analysis failed")


class CompanyProfile(TenantOwnedModel):
    """What the platform understands about the customer's own business.

    PRD section 26 ends with one sentence that shapes this whole model: "All
    AI-generated data must be editable." Editable is cheap; *staying* edited is
    the hard part, because re-analysis happens whenever the customer's site
    changes and the obvious implementation silently discards the corrections
    they made.

    So each field carries provenance. ``ai_values`` keeps what the model last
    said and ``edited_fields`` records what a human changed since; a re-run
    writes only into fields nobody has touched. A correction therefore survives
    every later analysis until it is explicitly reset -- and because the AI's
    version is still stored, the UI can offer both.

    One per organization: this is the company the customer *is*, not a company
    they are selling to. Prospects are a separate model.
    """

    #: Fields the agent populates, and therefore the ones edit-tracking covers.
    #: Everything generic -- serialisation, edit detection, reset -- iterates
    #: this, so adding a field to the schema means adding it here and nowhere
    #: else.
    AI_FIELDS: tuple[str, ...] = (
        "company_name",
        "one_line_summary",
        "industry",
        "business_model",
        "value_proposition",
        "pricing_summary",
        "products",
        "target_customers",
        "use_cases",
        "pain_points_solved",
        "geographies",
        "buyer_personas",
        "competitors",
    )

    website = models.URLField(_("website"), max_length=2048, blank=True)

    company_name = models.CharField(_("company name"), max_length=255, blank=True)
    one_line_summary = models.TextField(_("one-line summary"), blank=True)
    industry = models.CharField(_("industry"), max_length=120, blank=True)
    business_model = models.CharField(_("business model"), max_length=200, blank=True)
    value_proposition = models.TextField(_("value proposition"), blank=True)
    # Blank is a meaningful answer here, not a missing one: it means the site
    # publishes no pricing. Inventing a number is the failure the eval set
    # tests for, so the model must be able to represent "not stated".
    pricing_summary = models.TextField(_("pricing"), blank=True)

    products = models.JSONField(_("products"), default=list, blank=True)
    target_customers = models.JSONField(_("target customers"), default=list, blank=True)
    use_cases = models.JSONField(_("use cases"), default=list, blank=True)
    pain_points_solved = models.JSONField(_("pain points solved"), default=list, blank=True)
    geographies = models.JSONField(_("geographies"), default=list, blank=True)
    buyer_personas = models.JSONField(_("buyer personas"), default=list, blank=True)
    competitors = models.JSONField(_("competitors"), default=list, blank=True)

    # Provenance (PRD sections 58 and 61).
    evidence = models.JSONField(_("evidence"), default=list, blank=True)
    unknowns = models.JSONField(_("unknowns"), default=list, blank=True)
    confidence = models.CharField(_("confidence"), max_length=10, blank=True)
    source_snapshots = models.ManyToManyField(
        WebsiteSnapshot,
        related_name="company_profiles",
        blank=True,
        verbose_name=_("source snapshots"),
    )

    # What the agent last produced, before any human edit. Keeping it means a
    # correction can be undone, and means "what did the AI actually say?" stays
    # answerable after someone has edited the record.
    ai_values = models.JSONField(_("AI values"), default=dict, blank=True)
    edited_fields = models.JSONField(_("human-edited fields"), default=list, blank=True)

    status = models.CharField(
        _("status"), max_length=16, choices=ProfileStatus.choices, default=ProfileStatus.DRAFT
    )
    analysis_error = models.CharField(_("analysis error"), max_length=255, blank=True)
    prompt_pin = models.CharField(_("prompt version"), max_length=100, blank=True)
    last_analyzed_at = models.DateTimeField(_("last analyzed at"), null=True, blank=True)
    confirmed_at = models.DateTimeField(_("confirmed at"), null=True, blank=True)

    class Meta:
        verbose_name = _("company profile")
        verbose_name_plural = _("company profiles")
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization"], name="one_company_profile_per_organization"
            )
        ]

    def __str__(self) -> str:
        return self.company_name or self.website or str(self.public_id)

    @property
    def is_confirmed(self) -> bool:
        return self.status == ProfileStatus.CONFIRMED

    def was_edited(self, field: str) -> bool:
        return field in self.edited_fields

    def ai_value_for(self, field: str) -> Any:
        """What the agent last produced for a field, regardless of later edits."""
        return self.ai_values.get(field)
