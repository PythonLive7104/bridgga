"""The website sales audit (PRD sections 49 and 17).

A ``WebsiteAudit`` is the one record in this product that is **deliberately
not tenant-owned**, and the reason is worth stating because every other
customer-facing row here subclasses ``TenantOwnedModel`` on purpose.

Section 17 makes this a free acquisition tool: a stranger with no account
pastes a URL and gets something useful. There is no organization to scope the
result to at the moment it is created, and the result is meant to be shared --
its visibility rule is "whoever has the link", not "whoever is in the
workspace". Forcing it into the tenant model would mean inventing a tenant for
every anonymous visitor, and would describe the access rule as something it
is not.

So: ``organization`` records which workspace asked, when one did, and the
``public_id`` is the share token. Both are tested explicitly, because a model
that opts out of the generic isolation test has to earn it with tests of its
own.

The scores split the same way the engine does. Five dimensions are counted
from the HTML by ``audit_checks`` and three are judged by a model; a reader
can see which is which, and the audit still produces the measured five when
the model call fails.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import BaseModel


class AuditStatus(models.TextChoices):
    PENDING = "pending", _("Queued")
    RUNNING = "running", _("Running")
    READY = "ready", _("Ready")
    FAILED = "failed", _("Could not be completed")


class WebsiteAudit(BaseModel):
    """One audit of one page."""

    #: Normalised, and what the cache matches on: two people auditing the same
    #: site a minute apart should not cost two crawls and two model calls.
    url = models.URLField(_("URL"), max_length=2048, db_index=True)
    final_url = models.URLField(_("final URL"), max_length=2048, blank=True)
    domain = models.CharField(_("domain"), max_length=255, blank=True, db_index=True)

    # Nullable by design -- see the module docstring. This records who asked,
    # not who may read.
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="website_audits",
        verbose_name=_("requested by organization"),
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="website_audits",
        verbose_name=_("requested by"),
    )
    #: Section 17's "optional signup": a visitor may leave an address to have
    #: the result sent on. Optional means optional -- the audit runs and is
    #: shown in full without it.
    email = models.EmailField(_("email"), blank=True)

    status = models.CharField(
        _("status"), max_length=16, choices=AuditStatus.choices, default=AuditStatus.PENDING
    )
    error_reason = models.CharField(_("error"), max_length=255, blank=True)

    overall_score = models.PositiveSmallIntegerField(_("overall score"), default=0)
    #: {dimension: 0-100} for the dimensions that could be scored.
    scores = models.JSONField(_("scores"), default=dict, blank=True)
    #: Every measured check with what it found and how to fix it. The product.
    checks = models.JSONField(_("checks"), default=list, blank=True)
    #: Section 49's performance observations: measurements, never a score.
    performance = models.JSONField(_("performance observations"), default=list, blank=True)
    recommendations = models.JSONField(_("recommendations"), default=list, blank=True)
    notes = models.JSONField(_("notes per dimension"), default=dict, blank=True)

    what_they_sell = models.CharField(_("what they sell"), max_length=300, blank=True)
    who_its_for = models.CharField(_("who it is for"), max_length=300, blank=True)
    confidence = models.CharField(_("confidence"), max_length=10, blank=True)

    #: False when the model call failed and only the measured half ran. The
    #: audit is still served: five dimensions of checkable findings are worth
    #: more than an error page, and section 17 promised a useful free result.
    judged = models.BooleanField(_("judgement available"), default=False)

    page_title = models.CharField(_("page title"), max_length=300, blank=True)
    page_description = models.TextField(_("meta description"), blank=True)
    content_hash = models.CharField(_("content hash"), max_length=64, blank=True)
    page_bytes = models.PositiveIntegerField(_("page bytes"), default=0)
    elapsed_ms = models.FloatField(_("fetch time (ms)"), default=0.0)
    fetched_at = models.DateTimeField(_("fetched at"), null=True, blank=True)
    prompt_pin = models.CharField(_("prompt version"), max_length=100, blank=True)

    class Meta:
        verbose_name = _("website audit")
        verbose_name_plural = _("website audits")
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["url", "-created_at"], name="wsaudit_url_created_idx"),
            models.Index(fields=["organization", "-created_at"], name="wsaudit_org_created_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.url} ({self.status})"

    @property
    def is_ready(self) -> bool:
        return self.status == AuditStatus.READY

    @property
    def failed_checks(self) -> list[dict]:
        """What to fix, worst first, which is how the result should be read."""
        return sorted(
            (check for check in (self.checks or []) if not check.get("passed")),
            key=lambda check: -check.get("weight", 0),
        )

    @property
    def band(self) -> str:
        """Same thresholds as the opportunity score, for the same reason.

        One vocabulary for "how good is this" across the product: a reader who
        has learned what 75 means on a prospect should not have to learn it
        again here.
        """
        from apps.leads.scoring_models import band_for

        return band_for(self.overall_score)


__all__ = ["AuditStatus", "WebsiteAudit"]
