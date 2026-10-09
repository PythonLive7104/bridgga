"""Prospect research (PRD sections 34 and 35).

What the platform knows about *one* company, assembled for the moment someone
is about to contact it. It lives in the intelligence app beside
``CompanyProfile`` and ``ICP`` because all three are the same kind of thing --
what an agent made of some evidence, editable by the person who knows better.

Two decisions are worth stating.

**The reason-to-contact is stored in two fields, not one.** Section 35 requires
a concise explanation and then constrains it: "The explanation must be
evidence-based." A single text field cannot carry that constraint, because a
model asked for one sentence produces a fluent sentence and fluency is
indistinguishable from grounding once it is a string. Stored as an
``observation`` that must be supported by quoted evidence plus an
``implication`` about the seller's own product, it can be checked -- and
``apps.intelligence.research_agents`` does check it, dropping the reason
rather than storing one it cannot verify. ``reason_sentence`` joins them for
display, which is exactly the shape of section 35's worked example.

**One research record per company per ICP.** The same company is a different
prospect to two different ICPs: what to say to a cold-chain distributor about
fleet telematics is not what to say to a haulier about the same product. This
mirrors ``Lead``, which is scoped the same way and for the same reason.
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import AIEditableModel


class ResearchStatus(models.TextChoices):
    PENDING = "pending", _("Queued")
    RESEARCHING = "researching", _("Researching")
    READY = "ready", _("Ready")
    FAILED = "failed", _("Research failed")


class ProspectResearch(AIEditableModel):
    """A sales brief for one prospect (PRD section 34)."""

    AI_FIELDS: tuple[str, ...] = (
        "summary",
        "why_they_may_buy",
        "likely_pain",
        "possible_use_case",
        "suggested_approach",
        "personalization_points",
        "decision_maker_titles",
        "reason_observation",
        "reason_implication",
    )

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="research",
        verbose_name=_("company"),
    )
    # Nullable: a prospect can be researched before anybody has decided which
    # ICP it belongs to, and a workspace may run only one.
    icp = models.ForeignKey(
        "intelligence.ICP",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="research",
        verbose_name=_("ICP"),
    )

    summary = models.TextField(_("summary"), blank=True)
    why_they_may_buy = models.JSONField(_("why they may buy"), default=list, blank=True)
    likely_pain = models.JSONField(_("likely pain"), default=list, blank=True)
    possible_use_case = models.TextField(_("possible use case"), blank=True)
    suggested_approach = models.TextField(_("suggested approach"), blank=True)
    personalization_points = models.JSONField(_("personalization points"), default=list, blank=True)
    decision_maker_titles = models.JSONField(_("decision maker titles"), default=list, blank=True)

    # Section 35, split so the factual half can be verified. See the module
    # docstring for why this is not one text field.
    reason_observation = models.CharField(_("observation"), max_length=300, blank=True)
    reason_implication = models.CharField(_("implication"), max_length=300, blank=True)
    reason_evidence = models.JSONField(_("reason evidence"), default=list, blank=True)
    reason_confidence = models.CharField(_("reason confidence"), max_length=10, blank=True)
    #: Why a reason was not stored, when the agent produced one it could not
    #: verify. Kept because "no reason yet" and "the model made one up and we
    #: threw it away" call for different responses from a human.
    reason_rejected = models.CharField(_("reason rejected because"), max_length=255, blank=True)

    evidence = models.JSONField(_("evidence"), default=list, blank=True)
    unknowns = models.JSONField(_("unknowns"), default=list, blank=True)
    confidence = models.CharField(_("confidence"), max_length=10, blank=True)

    #: What was in view when this was written. Provenance (section 61) and the
    #: answer to "is this brief based on the signal I am looking at?".
    source_signals = models.ManyToManyField(
        "companies.LeadSignal",
        related_name="research",
        blank=True,
        verbose_name=_("source signals"),
    )
    source_snapshots = models.ManyToManyField(
        "intelligence.WebsiteSnapshot",
        related_name="research",
        blank=True,
        verbose_name=_("source snapshots"),
    )

    status = models.CharField(
        _("status"), max_length=16, choices=ResearchStatus.choices, default=ResearchStatus.PENDING
    )
    research_error = models.CharField(_("error"), max_length=255, blank=True)
    prompt_pin = models.CharField(_("prompt version"), max_length=100, blank=True)
    researched_at = models.DateTimeField(_("researched at"), null=True, blank=True)
    #: The opportunity score at the time of writing. Section 34 scopes research
    #: to high-value prospects, and this records what "high value" meant on the
    #: day -- the weighting is configurable, so the number alone is not enough
    #: to reconstruct the decision later.
    score_at_research = models.PositiveSmallIntegerField(
        _("score when researched"), null=True, blank=True
    )

    class Meta:
        verbose_name = _("prospect research")
        verbose_name_plural = _("prospect research")
        ordering = ["-researched_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "icp"], name="one_research_per_company_per_icp"
            )
        ]
        indexes = [
            models.Index(
                fields=["organization", "status", "-researched_at"],
                name="research_org_status_idx",
            )
        ]

    def __str__(self) -> str:
        return f"Research: {self.company_id}"

    @property
    def reason_sentence(self) -> str:
        """The section 35 explanation, as one string for display.

        Composed rather than stored. Keeping the two halves apart in the
        database is what lets the factual one be verified; keeping them joined
        here is what makes it readable. Storing the joined string as well
        would give it two sources of truth and one of them would drift.
        """
        if not self.reason_observation:
            return ""
        observation = self.reason_observation.rstrip(". ")
        implication = self.reason_implication.strip()
        if not implication:
            return f"{observation}."
        return f"{observation}. {implication[0].upper()}{implication[1:]}"

    @property
    def has_reason(self) -> bool:
        return bool(self.reason_observation and self.reason_evidence)

    @property
    def is_ready(self) -> bool:
        return self.status == ResearchStatus.READY


__all__ = ["ProspectResearch", "ResearchStatus"]
