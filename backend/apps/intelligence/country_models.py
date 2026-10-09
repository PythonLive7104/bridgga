"""Country intelligence and market recommendations (PRD sections 28, 70, 71).

Two models with very different jobs, and the split is the point:

``CountryProfile`` holds facts -- currency, languages, timezones, hubs, which
channels a business can actually be reached on, which data-protection law
applies. Platform-wide, seeded, and the same for every customer. It is not
AI-generated, because a currency code or a statute name is something to look
up, not something to infer.

``MarketRecommendation`` holds a judgement: given *this* company and *this*
ICP, how good a market is this, and why. Tenant-owned and AI-generated, with
the reasoning stored because PRD section 28 requires every recommendation to
explain itself.

Keeping them apart is what stops the agent inventing that Kenya uses the
shilling. The facts go into the prompt; only the judgement comes back.
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import BaseModel, TenantOwnedModel


class Channel(models.TextChoices):
    """Outbound channels (PRD section 70)."""

    EMAIL = "email", _("Email")
    WHATSAPP = "whatsapp", _("WhatsApp")
    LINKEDIN = "linkedin", _("LinkedIn")
    PHONE = "phone", _("Phone")
    SMS = "sms", _("SMS")


class CountryProfile(BaseModel):
    """What the platform knows about doing business in one country.

    Platform-wide rather than tenant-owned: these are facts about a country,
    not about a customer, and every workspace should see the same ones.
    """

    code = models.CharField(_("ISO 3166-1 alpha-2 code"), max_length=2, unique=True)
    name = models.CharField(_("name"), max_length=100)
    region = models.CharField(_("region"), max_length=60, blank=True)

    currency = models.CharField(_("currency"), max_length=3)
    languages = models.JSONField(_("languages"), default=list, blank=True)
    timezones = models.JSONField(_("timezones"), default=list, blank=True)

    major_industries = models.JSONField(_("major industries"), default=list, blank=True)
    business_hubs = models.JSONField(_("business hubs"), default=list, blank=True)

    # Ordered by preference (PRD section 70). The send path reads this to
    # decide what to offer, and a channel absent here is one the platform will
    # not suggest for this country.
    channels = models.JSONField(_("channel preference"), default=list, blank=True)
    communication_notes = models.TextField(_("communication notes"), blank=True)

    # Pointers to the law that applies, never advice about it. PRD section 62
    # requires legal review before production, and this field exists to tell
    # somebody what to take to that review.
    data_protection_law = models.CharField(_("data protection law"), max_length=200, blank=True)
    regulatory_notes = models.TextField(_("regulatory notes"), blank=True)

    is_launch_market = models.BooleanField(_("launch market"), default=False)
    metadata = models.JSONField(_("metadata"), default=dict, blank=True)

    class Meta:
        verbose_name = _("country profile")
        verbose_name_plural = _("country profiles")
        ordering = ["-is_launch_market", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"

    def summary_for_prompt(self) -> str:
        """The facts an agent may reason from, and must not contradict."""
        parts = [f"{self.name} ({self.code})"]
        if self.currency:
            parts.append(f"currency {self.currency}")
        if self.languages:
            parts.append(f"languages: {', '.join(self.languages)}")
        if self.business_hubs:
            parts.append(f"hubs: {', '.join(self.business_hubs)}")
        if self.major_industries:
            parts.append(f"industries: {', '.join(self.major_industries)}")
        if self.channels:
            parts.append(f"reachable by: {', '.join(self.channels)}")
        if self.data_protection_law:
            parts.append(f"data protection: {self.data_protection_law}")
        return " | ".join(parts)


class MarketFit(models.TextChoices):
    """The bands PRD section 28 uses in its own example."""

    HIGH = "high", _("High fit")
    MEDIUM_HIGH = "medium_high", _("Medium-high fit")
    MEDIUM = "medium", _("Medium fit")
    LOW = "low", _("Low fit")


class MarketRecommendation(TenantOwnedModel):
    """One country, judged against one customer's ICP.

    PRD section 28 ends with "Each recommendation must explain its reasoning",
    so ``reasoning`` is not decoration and is not optional in practice: a bare
    ranking is a number nobody can argue with, which makes it useless for a
    decision this consequential.
    """

    country = models.ForeignKey(
        CountryProfile,
        on_delete=models.CASCADE,
        related_name="recommendations",
        verbose_name=_("country"),
    )
    icp = models.ForeignKey(
        "intelligence.ICP",
        on_delete=models.CASCADE,
        related_name="market_recommendations",
        null=True,
        blank=True,
        verbose_name=_("generated for"),
    )

    fit = models.CharField(_("fit"), max_length=16, choices=MarketFit.choices)
    # 0-100, kept alongside the band so a list can be ordered finely while the
    # interface shows the coarse judgement the PRD asks for.
    score = models.PositiveSmallIntegerField(_("score"), default=0)
    rank = models.PositiveSmallIntegerField(_("rank"), default=0)

    reasoning = models.TextField(_("reasoning"))
    # The section 28 factors this judgement rested on, so a reader can see
    # which ones carried it rather than only the conclusion.
    factors = models.JSONField(_("factors"), default=dict, blank=True)
    recommended_channels = models.JSONField(_("recommended channels"), default=list, blank=True)
    cautions = models.JSONField(_("cautions"), default=list, blank=True)

    is_selected = models.BooleanField(_("selected by the customer"), default=False)
    prompt_pin = models.CharField(_("prompt version"), max_length=100, blank=True)

    class Meta:
        verbose_name = _("market recommendation")
        verbose_name_plural = _("market recommendations")
        ordering = ["rank", "-score"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "country"],
                name="one_recommendation_per_country_per_org",
            )
        ]
        indexes = [
            models.Index(fields=["organization", "-score"], name="market_org_score_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.country.name}: {self.get_fit_display()}"
