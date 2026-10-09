"""Leads and where they came from (PRD sections 60, 61, 80).

A ``Lead`` is not a company and not a person: it is the customer's *interest*
in one, with a status that moves. The same company can be a lead twice — once
for each ICP it matched — and separating the three means re-running discovery
does not disturb work already done on a prospect.

``LeadSource`` exists because section 61 requires a data provider's usage
rights to be reviewable. Without a named source with terms attached, "where
did this list come from, and are we allowed to use it?" is an investigation
rather than a query, and it is a question that gets asked at the worst moment.
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import TenantOwnedModel


class SourceKind(models.TextChoices):
    WEBSITE_CRAWL = "website_crawl", _("Website crawl")
    IMPORT = "import", _("File import")
    PROVIDER = "provider", _("Licensed data provider")
    MANUAL = "manual", _("Added by hand")
    API = "api", _("Public API")
    INTEGRATION = "integration", _("CRM integration")


class LeadSource(TenantOwnedModel):
    """A named origin for lead data, with the terms it arrived under."""

    name = models.CharField(_("name"), max_length=150)
    kind = models.CharField(_("kind"), max_length=20, choices=SourceKind.choices)

    # Section 61: "Data providers must be reviewed for legal and contractual
    # usage rights." These two fields are what make that review a record
    # rather than a memory, and what lets a lapsed licence be found by query.
    usage_license = models.CharField(_("usage licence"), max_length=200, blank=True)
    legal_review_at = models.DateTimeField(_("legally reviewed at"), null=True, blank=True)
    license_expires_at = models.DateTimeField(_("licence expires"), null=True, blank=True)

    notes = models.TextField(_("notes"), blank=True)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("lead source")
        verbose_name_plural = _("lead sources")
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name"], name="one_lead_source_name_per_org"
            )
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def needs_legal_review(self) -> bool:
        """True for a provider nobody has signed off, or whose terms lapsed.

        Only providers: a crawl of a public website and a customer's own file
        import are not third-party licences, and demanding a review for them
        would make the flag meaningless through sheer noise.
        """
        from django.utils import timezone

        if self.kind != SourceKind.PROVIDER:
            return False
        if self.legal_review_at is None:
            return True
        return self.license_expires_at is not None and self.license_expires_at <= timezone.now()


class LeadStatus(models.TextChoices):
    """Where a lead is in the work, before it becomes a CRM opportunity."""

    NEW = "new", _("New")
    RESEARCHING = "researching", _("Researching")
    QUALIFIED = "qualified", _("Qualified")
    ENROLLED = "enrolled", _("In a campaign")
    ENGAGED = "engaged", _("Replied")
    DISQUALIFIED = "disqualified", _("Disqualified")
    #: Kept out of campaigns without being deleted, so the reason survives.
    SUPPRESSED = "suppressed", _("Suppressed")


class Lead(TenantOwnedModel):
    """One company, considered as a prospect for one ICP."""

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="leads",
        verbose_name=_("company"),
    )
    # Nullable: a company is a lead before anybody at it has been identified,
    # and discovery routinely finds the business first and the person later.
    person = models.ForeignKey(
        "contacts.Person",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="leads",
        verbose_name=_("primary contact"),
    )
    icp = models.ForeignKey(
        "intelligence.ICP",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="leads",
        verbose_name=_("matched ICP"),
    )
    source = models.ForeignKey(
        LeadSource,
        on_delete=models.PROTECT,
        related_name="leads",
        verbose_name=_("source"),
    )

    status = models.CharField(
        _("status"),
        max_length=16,
        choices=LeadStatus.choices,
        default=LeadStatus.NEW,
        db_index=True,
    )
    # Written by the scoring engine in Phase 2.11, with its breakdown stored
    # alongside, because section 32 requires the platform to explain a score.
    score = models.PositiveSmallIntegerField(_("opportunity score"), default=0, db_index=True)
    score_breakdown = models.JSONField(_("score breakdown"), default=dict, blank=True)
    scored_at = models.DateTimeField(_("scored at"), null=True, blank=True)

    disqualified_reason = models.CharField(_("disqualified because"), max_length=255, blank=True)
    first_seen_at = models.DateTimeField(_("first seen"), null=True, blank=True)
    last_activity_at = models.DateTimeField(_("last activity"), null=True, blank=True)

    owner = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="owned_leads",
        verbose_name=_("owner"),
    )
    metadata = models.JSONField(_("metadata"), default=dict, blank=True)

    class Meta:
        verbose_name = _("lead")
        verbose_name_plural = _("leads")
        ordering = ["-score", "-created_at", "-id"]
        constraints = [
            # One lead per company per ICP. The same company legitimately
            # appears under two ICPs with different reasoning and different
            # scores; appearing twice under one is a duplicate, and duplicates
            # are how a person receives the same campaign twice.
            models.UniqueConstraint(
                fields=["organization", "company", "icp"],
                name="one_lead_per_company_per_icp",
            )
        ]
        indexes = [
            models.Index(fields=["organization", "status", "-score"], name="lead_org_status_idx"),
            models.Index(fields=["organization", "-score"], name="lead_org_score_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.company.name} ({self.status})"

    @property
    def is_contactable(self) -> bool:
        """Whether this lead may be enrolled in a campaign at all.

        Necessary, never sufficient: the send path checks the suppression list
        too (section 63), which is organization-wide and outlives any one lead.
        """
        if self.status in {LeadStatus.DISQUALIFIED, LeadStatus.SUPPRESSED}:
            return False
        return bool(self.person and self.person.can_be_emailed)


# Re-exported so the app registry discovers it and callers have one import
# path. Imports live in their own module because an upload with a mapping, a
# row-by-row outcome and a file on disk is a different subject to a lead, and
# the scoring weights because how a score is weighted is configuration rather
# than a lead.
from apps.leads.import_models import ImportJob, ImportStatus  # noqa: E402
from apps.leads.scoring_models import (  # noqa: E402
    DEFAULT_WEIGHTS,
    ScoreComponent,
    ScoringProfile,
)

__all__ = [
    "DEFAULT_WEIGHTS",
    "ImportJob",
    "ImportStatus",
    "Lead",
    "LeadSource",
    "LeadStatus",
    "ScoreComponent",
    "ScoringProfile",
    "SourceKind",
]
