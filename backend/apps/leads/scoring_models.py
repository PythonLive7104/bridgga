"""Scoring configuration (PRD section 32).

Section 32 gives an initial weighting and then one requirement: "Weights must
be configurable." They live in a tenant-owned row rather than in settings
because the right weighting is a property of a business, not of a deployment.
A recruitment agency lives on hiring signals; an infrastructure vendor cares
far more about technology fit and barely at all about a careers page.

Two decisions about the shape of that configuration.

**Weights are stored raw and normalised at scoring time.** A customer who sets
every weight to 10 has expressed "weigh these equally", not "produce a score
out of 80". Rejecting that would be pedantry, and silently scaling it to 100
would misreport what they chose, so the stored numbers stay theirs and the
engine divides by whatever they add up to.

**An unknown component is not a zero.** The engine drops components it cannot
assess and redistributes their weight across the rest -- see
``apps.leads.scoring``. The weight here is therefore a *relative* importance,
which is what makes the configuration survive a component arriving later:
engagement data does not exist until campaigns ship in Phase 3, and a score
that silently capped every prospect at 90 until then would be a lie told in
a number nobody could check.
"""

from __future__ import annotations

from typing import Any

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import TenantOwnedModel


class ScoreComponent(models.TextChoices):
    """The eight factors section 32 names, and only those."""

    ICP_FIT = "icp_fit", _("ICP fit")
    BUYING_INTENT = "buying_intent", _("Buying intent")
    PAIN_EVIDENCE = "pain_evidence", _("Pain evidence")
    COMPANY_GROWTH = "company_growth", _("Company growth")
    TECHNOLOGY_FIT = "technology_fit", _("Technology fit")
    GEOGRAPHIC_FIT = "geographic_fit", _("Geographic fit")
    CONTACT_QUALITY = "contact_quality", _("Contact quality")
    ENGAGEMENT = "engagement", _("Engagement")


#: Section 32's initial weighting, verbatim. Changing a number here changes
#: every organization that has not overridden it, so it belongs in review.
DEFAULT_WEIGHTS: dict[str, int] = {
    ScoreComponent.ICP_FIT: 25,
    ScoreComponent.BUYING_INTENT: 20,
    ScoreComponent.PAIN_EVIDENCE: 15,
    ScoreComponent.COMPANY_GROWTH: 10,
    ScoreComponent.TECHNOLOGY_FIT: 10,
    ScoreComponent.GEOGRAPHIC_FIT: 5,
    ScoreComponent.CONTACT_QUALITY: 5,
    ScoreComponent.ENGAGEMENT: 10,
}

MAX_WEIGHT = 100

#: Score bands. These must match ``scoreBand`` in web/src/lib/utils.ts: the
#: server names the band in the explainability payload and the interface
#: colours the badge, and a prospect labelled "high opportunity" in amber is
#: a bug report waiting to happen. A test asserts the thresholds.
BAND_THRESHOLDS: tuple[tuple[int, str], ...] = ((75, "high"), (45, "medium"), (0, "low"))


def band_for(score: int) -> str:
    for threshold, band in BAND_THRESHOLDS:
        if score >= threshold:
            return band
    return "low"


def default_weights() -> dict[str, int]:
    return dict(DEFAULT_WEIGHTS)


class ScoringProfile(TenantOwnedModel):
    """One organization's weighting of the section 32 components.

    One row per organization. Per-ICP weighting is a plausible extension --
    two ICPs can want genuinely different emphasis -- but nothing in section
    32 asks for it, and a second scope would double the explanation the
    interface has to give for a single number.
    """

    weights = models.JSONField(_("weights"), default=default_weights)
    notes = models.TextField(_("notes"), blank=True)
    updated_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scoring_profile_edits",
        verbose_name=_("last changed by"),
    )

    class Meta:
        verbose_name = _("scoring profile")
        verbose_name_plural = _("scoring profiles")
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization"], name="one_scoring_profile_per_organization"
            )
        ]

    def __str__(self) -> str:
        return f"Scoring weights for {self.organization_id}"

    def resolved_weights(self) -> dict[str, int]:
        """The stored weights, cleaned up.

        Unknown keys are dropped and missing ones defaulted, so a component
        added in a later release scores on its default weight rather than at
        zero, and a component removed from the vocabulary stops counting
        without anybody having to migrate the JSON.
        """
        return merge_weights(self.weights)

    @property
    def is_customised(self) -> bool:
        return self.resolved_weights() != DEFAULT_WEIGHTS


def merge_weights(raw: Any) -> dict[str, int]:
    """Coerce stored or submitted weights into a complete, valid mapping."""
    weights = default_weights()
    if not isinstance(raw, dict):
        return weights

    for key, value in raw.items():
        if key not in weights:
            continue
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        weights[key] = max(0, min(number, MAX_WEIGHT))

    # Every weight zero would make the score undefined rather than zero, so
    # the defaults stand in. Deliberately not an error: this arrives from a
    # form where clearing every field is an easy accident.
    if not any(weights.values()):
        return default_weights()
    return weights


def weights_for(organization: Any) -> dict[str, int]:
    """The organization's weights, or section 32's defaults if it has none."""
    profile = ScoringProfile.all_objects.filter(organization_id=organization.pk).first()
    return profile.resolved_weights() if profile else default_weights()


__all__ = [
    "BAND_THRESHOLDS",
    "DEFAULT_WEIGHTS",
    "MAX_WEIGHT",
    "ScoreComponent",
    "ScoringProfile",
    "band_for",
    "default_weights",
    "merge_weights",
    "weights_for",
]
