"""Companies, their technology and their events (PRD sections 30, 31, 80).

A ``Company`` here is a *prospect* -- a business the customer might sell to.
It is not ``intelligence.CompanyProfile``, which is the customer's own
business. The two are easy to confuse and model entirely different things, so
they live in different apps.

Everything in this module carries provenance (section 61). A prospect record
is assembled from crawls, imports and providers, and a row whose origin is
unknown cannot be defended to the customer who acts on it, nor dropped when a
provider contract ends.
"""

from __future__ import annotations

from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import ProvenancedModel, TenantOwnedModel


class CompanyStatus(models.TextChoices):
    ACTIVE = "active", _("Active")
    #: Kept rather than deleted: the evidence that a company was considered and
    #: rejected is worth as much as the ones that were not.
    DISQUALIFIED = "disqualified", _("Disqualified")
    DUPLICATE = "duplicate", _("Merged into another record")
    CLOSED = "closed", _("No longer trading")


class EmployeeRange(models.TextChoices):
    """Bands rather than a number.

    Published headcounts are estimates with a wide error bar, and storing
    "47 employees" implies a precision the source does not have. Section 29
    searches on a range anyway.
    """

    MICRO = "1-10", _("1-10")
    SMALL = "11-50", _("11-50")
    MEDIUM = "51-200", _("51-200")
    LARGE = "201-500", _("201-500")
    XLARGE = "501-1000", _("501-1000")
    ENTERPRISE = "1000+", _("1000+")


class Company(TenantOwnedModel, ProvenancedModel):
    """A prospect company (PRD sections 30 and 31)."""

    name = models.CharField(_("name"), max_length=255)
    legal_name = models.CharField(_("legal name"), max_length=255, blank=True)

    website = models.URLField(_("website"), max_length=2048, blank=True)
    # The deduplication key. Normalised on save -- lowercased, `www.` removed,
    # scheme and path stripped -- because "https://www.Acme.com/" and
    # "acme.com" are one company, and a prospect list that contains both is a
    # list that emails somebody twice.
    domain = models.CharField(_("domain"), max_length=255, blank=True, db_index=True)

    description = models.TextField(_("description"), blank=True)
    industry = models.CharField(_("industry"), max_length=120, blank=True, db_index=True)
    sub_industry = models.CharField(_("sub-industry"), max_length=120, blank=True)

    country = models.CharField(_("country"), max_length=2, blank=True, db_index=True)
    city = models.CharField(_("city"), max_length=120, blank=True)
    region = models.CharField(_("region"), max_length=120, blank=True)

    employee_range = models.CharField(
        _("employee range"), max_length=16, choices=EmployeeRange.choices, blank=True
    )
    revenue_range = models.CharField(_("revenue range"), max_length=60, blank=True)
    business_model = models.CharField(_("business model"), max_length=120, blank=True)
    founded_year = models.PositiveSmallIntegerField(_("founded"), null=True, blank=True)

    # Public business contact details only (section 30). Personal addresses
    # belong on a Person, under that model's consent rules.
    phone = models.CharField(_("public phone"), max_length=40, blank=True)
    emails = models.JSONField(_("public emails"), default=list, blank=True)
    linkedin_url = models.URLField(_("LinkedIn"), max_length=500, blank=True)
    social_links = models.JSONField(_("social links"), default=list, blank=True)

    status = models.CharField(
        _("status"), max_length=16, choices=CompanyStatus.choices, default=CompanyStatus.ACTIVE
    )
    merged_into = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="duplicates",
        verbose_name=_("merged into"),
    )

    enriched_at = models.DateTimeField(_("last enriched"), null=True, blank=True)
    metadata = models.JSONField(_("metadata"), default=dict, blank=True)

    class Meta:
        verbose_name = _("company")
        verbose_name_plural = _("companies")
        ordering = ["name", "id"]
        constraints = [
            # At most one *active* company per domain. Two conditions, for two
            # different reasons:
            #
            # - a company with no website is still a company, and without the
            #   first condition every domain-less row would collide;
            # - a merged duplicate keeps its domain, because that domain is
            #   evidence of where the company was found, and the alternative
            #   (blanking it) destroys provenance to satisfy an index.
            models.UniqueConstraint(
                fields=["organization", "domain"],
                condition=~models.Q(domain="") & ~models.Q(status=CompanyStatus.DUPLICATE),
                name="one_active_company_per_domain_per_org",
            )
        ]
        indexes = [
            models.Index(fields=["organization", "country"], name="company_org_country_idx"),
            models.Index(fields=["organization", "industry"], name="company_org_industry_idx"),
            models.Index(fields=["organization", "status"], name="company_org_status_idx"),
            # Composites for the filter pairs a prospect list actually uses
            # together (PRD section 29). Two single-column scans and a merge
            # is slower than one range read.
            models.Index(
                fields=["organization", "country", "industry"],
                name="company_org_geo_industry_idx",
            ),
            models.Index(
                fields=["organization", "status", "country"], name="company_org_status_geo_idx"
            ),
            # Postgres only; created by migration 0003 and skipped on SQLite.
            GinIndex(fields=["name"], name="company_name_trgm_idx", opclasses=["gin_trgm_ops"]),
            GinIndex(
                fields=["industry"],
                name="company_industry_trgm_idx",
                opclasses=["gin_trgm_ops"],
            ),
        ]

    def __str__(self) -> str:
        return self.name

    def save(self, *args: object, **kwargs: object) -> None:
        self.domain = normalise_domain(self.domain or self.website)
        super().save(*args, **kwargs)  # type: ignore[arg-type]


def normalise_domain(value: str) -> str:
    """Reduce a URL or host to the key two records are compared on.

    Keeps the registrable host and nothing else, so scheme, `www.`, port, path
    and case cannot produce two rows for one company. Deliberately *not* a
    public-suffix-aware parse: `acme.co.uk` and `acme.com` are different
    companies and must stay different keys.
    """
    from urllib.parse import urlsplit

    candidate = (value or "").strip().lower()
    if not candidate:
        return ""
    if "://" not in candidate:
        candidate = f"//{candidate}"

    host = urlsplit(candidate).hostname or ""
    return host.removeprefix("www.")[:255]


class CompanyTechnology(TenantOwnedModel, ProvenancedModel):
    """A technology observed in use at a company (PRD sections 29, 30).

    ``last_seen`` is what makes this useful as a signal rather than a label: a
    technology that stopped appearing is a change, and section 33 lists
    technology change as a buying signal.
    """

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="technologies", verbose_name=_("company")
    )
    name = models.CharField(_("technology"), max_length=120)
    category = models.CharField(_("category"), max_length=80, blank=True)

    first_seen = models.DateTimeField(_("first seen"), null=True, blank=True)
    last_seen = models.DateTimeField(_("last seen"), null=True, blank=True, db_index=True)
    is_current = models.BooleanField(_("currently in use"), default=True)

    class Meta:
        verbose_name = _("company technology")
        verbose_name_plural = _("company technologies")
        ordering = ["company_id", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "name"], name="one_technology_row_per_company"
            )
        ]

    def __str__(self) -> str:
        return f"{self.name} @ {self.company_id}"


class CompanyEvent(TenantOwnedModel, ProvenancedModel):
    """Something observable that happened at a company (PRD sections 31, 33).

    ``event_type`` draws on the same closed vocabulary as an ICP's pain
    signals (``apps.ai.schemas.SignalType``). That is the join: an ICP that
    says it watches for `hiring` matches a company event of type `hiring`,
    and neither side can drift into free text that matches nothing.
    """

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="events", verbose_name=_("company")
    )
    event_type = models.CharField(_("type"), max_length=40, db_index=True)
    title = models.CharField(_("title"), max_length=300)
    description = models.TextField(_("description"), blank=True)

    occurred_at = models.DateTimeField(_("occurred at"), null=True, blank=True, db_index=True)
    # Separate from `source_url`: provenance records where *we* read it, which
    # may be an aggregator, while this is what the event itself points at.
    url = models.URLField(_("link"), max_length=2048, blank=True)

    class Meta:
        verbose_name = _("company event")
        verbose_name_plural = _("company events")
        ordering = ["-occurred_at", "-id"]
        indexes = [
            models.Index(
                fields=["organization", "event_type", "-occurred_at"],
                name="event_org_type_date_idx",
            ),
            models.Index(
                fields=["company", "event_type", "-occurred_at"],
                name="event_company_type_date_idx",
            ),
        ]

    def __str__(self) -> str:
        return self.title


# Re-exported for the app registry and a single import path.
from apps.companies.saved_searches import SavedSearch  # noqa: E402

__all__ = [
    "Company",
    "CompanyEvent",
    "CompanyStatus",
    "CompanyTechnology",
    "EmployeeRange",
    "SavedSearch",
    "normalise_domain",
]
