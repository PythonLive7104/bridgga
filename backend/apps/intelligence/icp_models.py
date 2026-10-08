"""Ideal customer profile (PRD section 27).

Kept in its own module rather than appended to ``models.py`` because the two
describe different things: that file is about reading a website, this is about
deciding who to sell to. Both are imported by ``models``, so Django's app
registry sees them as one app.
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import AIEditableModel


class ICPStatus(models.TextChoices):
    DRAFT = "draft", _("Draft")
    GENERATING = "generating", _("Generating")
    READY = "ready", _("Ready for review")
    ACTIVE = "active", _("Active")
    FAILED = "failed", _("Generation failed")


class ICP(AIEditableModel):
    """Who the customer should sell to.

    Several per organization, because a real business sells to more than one
    kind of buyer -- a logistics platform may target haulage fleets and
    cold-chain distributors with different sizes, buyers and signals. One is
    marked ``is_active``: the default that prospect discovery and campaigns
    use when nothing else is chosen.

    Editable throughout, on the same terms as ``CompanyProfile``: section 27
    ends with "Allow manual editing", and the customer knows their market
    better than the agent read it off a website.
    """

    AI_FIELDS: tuple[str, ...] = (
        "name",
        "industries",
        "countries",
        "employee_range",
        "business_size",
        "business_models",
        "technologies",
        "growth_stage",
        "job_titles",
        "departments",
        "seniority",
        "responsibilities",
        "pain_signals",
        "rationale",
    )

    name = models.CharField(_("name"), max_length=120, blank=True)

    # Company profile (section 27, first block).
    industries = models.JSONField(_("industries"), default=list, blank=True)
    countries = models.JSONField(_("countries"), default=list, blank=True)
    employee_range = models.CharField(_("employee range"), max_length=60, blank=True)
    business_size = models.CharField(_("estimated business size"), max_length=60, blank=True)
    business_models = models.JSONField(_("business models"), default=list, blank=True)
    technologies = models.JSONField(_("technologies"), default=list, blank=True)
    growth_stage = models.CharField(_("growth stage"), max_length=60, blank=True)

    # Buyer profile (section 27, second block). Flattened rather than nested in
    # one JSON column so each part is independently editable and independently
    # revertible -- a customer correcting the job titles should not have to
    # re-accept the agent's guess at seniority.
    job_titles = models.JSONField(_("job titles"), default=list, blank=True)
    departments = models.JSONField(_("departments"), default=list, blank=True)
    seniority = models.JSONField(_("seniority"), default=list, blank=True)
    responsibilities = models.JSONField(_("responsibilities"), default=list, blank=True)

    # Pain signals (section 27, third block), each carrying a type from the
    # closed vocabulary in apps.ai.schemas.SignalType. That type is what lets
    # the signal engine in section 33 match a detected event to this ICP.
    pain_signals = models.JSONField(_("pain signals"), default=list, blank=True)

    rationale = models.TextField(_("rationale"), blank=True)
    evidence = models.JSONField(_("evidence"), default=list, blank=True)
    confidence = models.CharField(_("confidence"), max_length=10, blank=True)

    source_profile = models.ForeignKey(
        "intelligence.CompanyProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="icps",
        verbose_name=_("generated from"),
    )

    status = models.CharField(
        _("status"), max_length=16, choices=ICPStatus.choices, default=ICPStatus.DRAFT
    )
    generation_error = models.CharField(_("generation error"), max_length=255, blank=True)
    prompt_pin = models.CharField(_("prompt version"), max_length=100, blank=True)
    is_active = models.BooleanField(_("active"), default=False)

    class Meta:
        verbose_name = _("ideal customer profile")
        verbose_name_plural = _("ideal customer profiles")
        ordering = ["-is_active", "-created_at", "-id"]
        constraints = [
            # Partial unique index: many inactive ICPs, at most one active.
            # Enforced in the database rather than in a service, because two
            # concurrent activations would otherwise both pass a read check.
            models.UniqueConstraint(
                fields=["organization"],
                condition=models.Q(is_active=True),
                name="one_active_icp_per_organization",
            )
        ]
        indexes = [
            models.Index(fields=["organization", "status"], name="icp_org_status_idx"),
        ]

    def __str__(self) -> str:
        return self.name or str(self.public_id)

    def signal_types(self) -> list[str]:
        """The signal types this ICP watches for, for the section 33 engine."""
        return [
            entry["type"]
            for entry in self.pain_signals
            if isinstance(entry, dict) and entry.get("type")
        ]
