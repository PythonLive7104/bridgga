"""Buying signals (PRD section 33).

A ``LeadSignal`` is an *interpretation*, and that is what separates it from
``CompanyEvent`` next door. The distinction is worth stating because the two
models look similar enough to invite a merge:

* A ``CompanyEvent`` is a fact about the world. "Acme closed a Series A on 3
  March" is true in 2031 exactly as it was in 2026, so an event is permanent
  history and never expires.
* A ``LeadSignal`` is a claim that something observable about a company makes
  it worth a conversation *now*. Section 33 requires every signal to carry an
  expiration for precisely that reason: a funding round from three years ago
  is history, not intent, and a signal that cannot go stale would keep a dead
  prospect at the top of a list forever.

So events are the raw feed, signals are what the detectors make of it, and a
signal keeps a link back to the event or the snapshot it was derived from.
``apps.companies.detectors`` holds the detectors; the scoring that consumes
these is section 32.

**Decay rather than a cliff.** ``expires_at`` is the hard end, but a signal's
usefulness falls off before it reaches it, so ``decayed_strength`` tapers the
raw strength towards zero across the signal's life. A hiring post from
yesterday and one from seven weeks ago are both inside the window and are not
worth the same.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.ai.schemas import SignalType
from apps.common.managers import AllObjectsManager, TenantManager, TenantQuerySet
from apps.common.models import ProvenancedModel, TenantOwnedModel

#: Built from the enum so the vocabulary cannot drift. ``SignalType`` is the
#: join between what an ICP says it watches for and what the engine detects
#: (see its docstring), and a second hand-written list of choices here would
#: be one edit away from matching nothing.
SIGNAL_TYPE_CHOICES: list[tuple[str, str]] = [
    (member.value, member.value.replace("_", " ").capitalize()) for member in SignalType
]

#: How long each kind of signal stays actionable, in days.
#:
#: These are judgements about sales reality, not measurements. A funding round
#: is worth mentioning for two quarters; a changed homepage is barely worth
#: mentioning in a month. They are deliberately generous rather than tight:
#: expiry removes a signal from the active set entirely, and the decay curve
#: already discounts age within the window.
SIGNAL_TTL_DAYS: dict[str, int] = {
    SignalType.FUNDING: 180,
    SignalType.ACQUISITION: 180,
    SignalType.EXPANSION: 120,
    SignalType.NEW_OFFICE: 120,
    SignalType.LEADERSHIP_CHANGE: 120,
    SignalType.TECHNOLOGY_CHANGE: 120,
    SignalType.PRODUCT_LAUNCH: 90,
    SignalType.PRICING_CHANGE: 90,
    SignalType.HIRING: 60,
    SignalType.PROCUREMENT: 60,
    SignalType.NEW_PAGES: 45,
    SignalType.ADVERTISING: 45,
    SignalType.CONTENT_GROWTH: 45,
    SignalType.WEBSITE_CHANGE: 30,
    SignalType.SOCIAL_ACTIVITY: 30,
    SignalType.OTHER: 60,
}

DEFAULT_SIGNAL_TTL_DAYS = 60

#: Floor on the decay curve. A signal inside its window is never worth nothing
#: -- if it were, it should have expired instead.
MIN_FRESHNESS = 0.15


def ttl_days_for(signal_type: str) -> int:
    """How long a signal of this type stays active.

    Overridable through ``SIGNAL_TTL_DAYS`` in settings, because the right
    window differs by industry: a staffing firm cares about a hiring post for
    a fortnight, an enterprise-software seller for a quarter.
    """
    overrides = getattr(settings, "SIGNAL_TTL_DAYS", None) or {}
    if signal_type in overrides:
        return int(overrides[signal_type])
    return SIGNAL_TTL_DAYS.get(signal_type, DEFAULT_SIGNAL_TTL_DAYS)


def expiry_for(signal_type: str, *, start: datetime) -> datetime:
    return start + timedelta(days=ttl_days_for(signal_type))


class LeadSignalQuerySet(TenantQuerySet):
    """Query helpers for the one question callers always ask."""

    def active(self, *, at: datetime | None = None) -> LeadSignalQuerySet:
        """Signals that are neither expired nor dismissed.

        Nearly every read wants this, and spelling it out at each call site is
        how a dismissed signal ends up back in a prospect list.
        """
        moment = at or timezone.now()
        return self.filter(dismissed_at__isnull=True, expires_at__gt=moment)

    def expired(self, *, at: datetime | None = None) -> LeadSignalQuerySet:
        return self.filter(expires_at__lte=at or timezone.now())

    def of_type(self, types: list[str] | tuple[str, ...]) -> LeadSignalQuerySet:
        return self.filter(signal_type__in=list(types))

    def detected_within(self, days: int) -> LeadSignalQuerySet:
        return self.filter(detected_at__gte=timezone.now() - timedelta(days=days))

    def strongest_first(self) -> LeadSignalQuerySet:
        return self.order_by("-strength", "-detected_at", "-id")


class LeadSignalManager(TenantManager.from_queryset(LeadSignalQuerySet)):  # type: ignore[misc]
    pass


class AllLeadSignalsManager(AllObjectsManager.from_queryset(LeadSignalQuerySet)):  # type: ignore[misc]
    pass


class LeadSignal(TenantOwnedModel, ProvenancedModel):
    """One reason, with evidence, that a company is worth contacting now.

    The fields section 33 names map as follows: ``signal_type`` is the type,
    ``source``/``source_url`` come from ``ProvenancedModel``, ``occurred_at``
    and ``detected_at`` are the timestamps, ``confidence`` is inherited,
    ``evidence`` is the quoted support, and ``expires_at`` is the staleness.
    """

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="signals",
        verbose_name=_("company"),
    )

    signal_type = models.CharField(
        _("type"), max_length=40, choices=SIGNAL_TYPE_CHOICES, db_index=True
    )
    title = models.CharField(_("title"), max_length=300)
    description = models.TextField(_("description"), blank=True)

    #: Which detector produced this, e.g. ``hiring_page``. Kept so a detector
    #: that turns out to be noisy can have its output found and retired
    #: without touching anything else's.
    detector = models.CharField(_("detector"), max_length=60, blank=True, db_index=True)

    #: Identity of the *observation*, not of the row: a hash of whatever makes
    #: this signal the thing it is -- the set of job titles on a careers page,
    #: the prices on a pricing page. Re-running a detector over an unchanged
    #: page therefore refreshes one row instead of appending a duplicate every
    #: hour, and a genuinely changed page produces a new signal.
    fingerprint = models.CharField(_("fingerprint"), max_length=64)

    #: When the thing happened, where that is knowable. Null is honest and
    #: common: a careers page says a role is open, not when it was posted.
    occurred_at = models.DateTimeField(_("occurred at"), null=True, blank=True, db_index=True)
    detected_at = models.DateTimeField(_("first detected"), default=timezone.now, db_index=True)
    last_seen_at = models.DateTimeField(_("last confirmed"), null=True, blank=True)
    expires_at = models.DateTimeField(_("expires at"), db_index=True)

    #: 0-100 before decay. Set by the detector from how much the observation
    #: actually supports: three open fleet-manager roles is a stronger hiring
    #: signal than one, and a changed price is stronger than a changed footer.
    strength = models.PositiveSmallIntegerField(_("strength"), default=50)

    #: ``apps.ai.schemas.Evidence`` entries, as JSON. Section 58: every claim
    #: carries its source, and this is the part a human checks before trusting
    #: the signal enough to mention it in a message.
    evidence = models.JSONField(_("evidence"), default=list, blank=True)

    source_event = models.ForeignKey(
        "companies.CompanyEvent",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="signals",
        verbose_name=_("source event"),
    )
    source_snapshot = models.ForeignKey(
        "intelligence.WebsiteSnapshot",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="signals",
        verbose_name=_("source snapshot"),
    )

    #: A human saying "not relevant". Recorded rather than deleted, so the
    #: detector's output can be judged later and so re-detection does not
    #: quietly overrule the person who dismissed it.
    dismissed_at = models.DateTimeField(_("dismissed at"), null=True, blank=True)
    dismissed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dismissed_signals",
        verbose_name=_("dismissed by"),
    )
    dismiss_reason = models.CharField(_("dismiss reason"), max_length=255, blank=True)

    metadata = models.JSONField(_("metadata"), default=dict, blank=True)

    objects = LeadSignalManager()
    all_objects = AllLeadSignalsManager()

    class Meta:
        verbose_name = _("lead signal")
        verbose_name_plural = _("lead signals")
        ordering = ["-detected_at", "-id"]
        # Unfiltered, because Django uses the base manager for related-object
        # descriptors and a tenant-scoped one there breaks a foreign-key fetch
        # made outside a request.
        base_manager_name = "all_objects"
        constraints = [
            # One row per observation. Without this, an hourly detector run
            # turns one open role into 168 signals a week and the prospect
            # table becomes unreadable.
            models.UniqueConstraint(
                fields=["company", "signal_type", "fingerprint"],
                name="one_signal_per_company_type_fingerprint",
            ),
            models.CheckConstraint(
                condition=models.Q(strength__gte=0) & models.Q(strength__lte=100),
                name="signal_strength_is_a_percentage",
            ),
        ]
        indexes = [
            # The prospect-list query: this organization's live signals of a
            # given type, newest first.
            models.Index(
                fields=["organization", "signal_type", "-detected_at"],
                name="signal_org_type_date_idx",
            ),
            models.Index(fields=["organization", "expires_at"], name="signal_org_expiry_idx"),
            models.Index(fields=["company", "-detected_at"], name="signal_company_date_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.signal_type}: {self.title}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        # A signal with no expiry is a signal that never goes stale, which
        # section 33 forbids. Derived rather than required of every caller.
        if not self.expires_at:
            self.expires_at = expiry_for(
                self.signal_type, start=self.occurred_at or self.detected_at or timezone.now()
            )
        super().save(*args, **kwargs)

    # ----------------------------------------------------------------- state

    @property
    def is_dismissed(self) -> bool:
        return self.dismissed_at is not None

    def is_expired(self, *, at: datetime | None = None) -> bool:
        return self.expires_at <= (at or timezone.now())

    def is_active(self, *, at: datetime | None = None) -> bool:
        return not self.is_dismissed and not self.is_expired(at=at)

    # ------------------------------------------------------------------ age

    @property
    def observed_at(self) -> datetime:
        """When the clock starts for decay purposes."""
        return self.occurred_at or self.detected_at

    def age_days(self, *, at: datetime | None = None) -> int:
        return max(((at or timezone.now()) - self.observed_at).days, 0)

    def freshness(self, *, at: datetime | None = None) -> float:
        """1.0 when just observed, falling to ``MIN_FRESHNESS`` at expiry.

        Linear, not exponential. The curve is a modelling choice nobody can
        calibrate yet, and a straight line is the one a customer can predict
        from the two numbers the interface already shows them.
        """
        moment = at or timezone.now()
        if moment >= self.expires_at:
            return 0.0

        span = (self.expires_at - self.observed_at).total_seconds()
        if span <= 0:
            return 1.0

        remaining = (self.expires_at - moment).total_seconds() / span
        return round(MIN_FRESHNESS + (1.0 - MIN_FRESHNESS) * min(max(remaining, 0.0), 1.0), 4)

    def decayed_strength(self, *, at: datetime | None = None) -> int:
        """Strength discounted for age. What section 32 should score on."""
        if not self.is_active(at=at):
            return 0
        return round(self.strength * self.freshness(at=at))


__all__ = [
    "DEFAULT_SIGNAL_TTL_DAYS",
    "MIN_FRESHNESS",
    "SIGNAL_TTL_DAYS",
    "SIGNAL_TYPE_CHOICES",
    "LeadSignal",
    "LeadSignalQuerySet",
    "expiry_for",
    "ttl_days_for",
]
