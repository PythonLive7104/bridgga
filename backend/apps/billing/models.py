"""Billing foundation (PRD sections 67 to 69).

Phase 1 ships the shape only: plans, subscriptions, a credit ledger and a usage
record. No checkout, no provider calls -- those arrive in Phase 4 once there is
something worth charging for.

Two decisions here are hard to change later, so they are made now:

* Money is stored as integer minor units (kobo, cents) plus a currency code.
  Floats lose money, and a single column cannot represent NGN and USD at once.
* Credits are an append-only ledger, not a mutable balance column. A balance
  that can be overwritten cannot be reconciled when a customer disputes it, and
  concurrent AI jobs would race on it.
"""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Sum
from django.utils.translation import gettext_lazy as _

from apps.common.models import BaseModel, TenantOwnedModel


class PlanTier(models.TextChoices):
    FREE = "free", _("Free")
    STARTER = "starter", _("Starter")
    GROWTH = "growth", _("Growth")
    AGENCY = "agency", _("Agency")
    ENTERPRISE = "enterprise", _("Enterprise")


class PaymentProvider(models.TextChoices):
    # African payment rails first (PRD section 67).
    BACHS = "bachs", _("Bachs")
    PAYSTACK = "paystack", _("Paystack")
    FLUTTERWAVE = "flutterwave", _("Flutterwave")
    STRIPE = "stripe", _("Stripe")
    MANUAL = "manual", _("Manual / invoice")


class Plan(BaseModel):
    """A purchasable plan. Platform-wide, not tenant-owned."""

    tier = models.CharField(_("tier"), max_length=32, choices=PlanTier.choices, unique=True)
    name = models.CharField(_("name"), max_length=100)
    description = models.TextField(_("description"), blank=True)

    monthly_price_minor = models.BigIntegerField(_("monthly price (minor units)"), default=0)
    currency = models.CharField(_("currency"), max_length=3, default="USD")

    # Quotas. Null means unlimited, which is different from zero.
    included_credits = models.IntegerField(_("included monthly credits"), default=0)
    max_seats = models.IntegerField(_("max seats"), null=True, blank=True)
    max_workspaces = models.IntegerField(_("max workspaces"), null=True, blank=True)
    max_prospects_per_month = models.IntegerField(
        _("max prospects per month"), null=True, blank=True
    )

    is_public = models.BooleanField(_("publicly selectable"), default=True)
    sort_order = models.IntegerField(_("sort order"), default=0)

    class Meta:
        verbose_name = _("plan")
        verbose_name_plural = _("plans")
        ordering = ["sort_order", "monthly_price_minor"]

    def __str__(self) -> str:
        return self.name

    @property
    def monthly_price(self) -> Decimal:
        return Decimal(self.monthly_price_minor) / 100


class SubscriptionStatus(models.TextChoices):
    TRIALING = "trialing", _("Trialing")
    ACTIVE = "active", _("Active")
    PAST_DUE = "past_due", _("Past due")
    PAUSED = "paused", _("Paused")
    CANCELED = "canceled", _("Canceled")


class Subscription(TenantOwnedModel):
    """One organization's current plan."""

    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscriptions")
    status = models.CharField(
        _("status"),
        max_length=32,
        choices=SubscriptionStatus.choices,
        default=SubscriptionStatus.TRIALING,
    )

    provider = models.CharField(
        _("provider"),
        max_length=32,
        choices=PaymentProvider.choices,
        default=PaymentProvider.MANUAL,
    )
    provider_customer_id = models.CharField(_("provider customer id"), max_length=200, blank=True)
    provider_subscription_id = models.CharField(
        _("provider subscription id"), max_length=200, blank=True
    )

    seats = models.IntegerField(_("seats"), default=1)
    currency = models.CharField(_("currency"), max_length=3, default="USD")

    current_period_start = models.DateTimeField(_("period start"), null=True, blank=True)
    current_period_end = models.DateTimeField(_("period end"), null=True, blank=True)
    trial_ends_at = models.DateTimeField(_("trial ends at"), null=True, blank=True)
    canceled_at = models.DateTimeField(_("canceled at"), null=True, blank=True)

    class Meta:
        verbose_name = _("subscription")
        verbose_name_plural = _("subscriptions")
        constraints = [
            # An organization has exactly one live subscription at a time.
            models.UniqueConstraint(
                fields=["organization"],
                condition=~models.Q(status="canceled"),
                name="subscription_one_live_per_org",
            )
        ]

    def __str__(self) -> str:
        return f"{self.organization} on {self.plan} ({self.status})"

    @property
    def is_live(self) -> bool:
        return self.status in {SubscriptionStatus.TRIALING, SubscriptionStatus.ACTIVE}


class CreditEntryReason(models.TextChoices):
    PLAN_ALLOWANCE = "plan_allowance", _("Monthly plan allowance")
    PURCHASE = "purchase", _("Credit purchase")
    ADJUSTMENT = "adjustment", _("Manual adjustment")
    REFUND = "refund", _("Refund")
    CONSUMPTION = "consumption", _("Consumption")
    EXPIRY = "expiry", _("Expiry")


class CreditEntry(TenantOwnedModel):
    """Append-only credit ledger. Positive grants, negative consumption."""

    amount = models.IntegerField(
        _("amount"), help_text=_("Positive to grant credits, negative to consume them.")
    )
    reason = models.CharField(_("reason"), max_length=32, choices=CreditEntryReason.choices)
    description = models.CharField(_("description"), max_length=255, blank=True)

    # What consumed the credits, for the per-feature cost reporting in PRD
    # section 59.
    feature = models.CharField(_("feature"), max_length=64, blank=True)
    reference = models.CharField(_("reference"), max_length=200, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="credit_entries_created",
    )

    class Meta:
        verbose_name = _("credit entry")
        verbose_name_plural = _("credit ledger")
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["organization", "-created_at"], name="credit_org_created_idx"),
            models.Index(fields=["organization", "feature"], name="credit_org_feature_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.amount:+d} credits ({self.reason})"

    @staticmethod
    def balance_for(organization: object) -> int:
        organization_id = getattr(organization, "pk", organization)
        total = CreditEntry.all_objects.filter(organization_id=organization_id).aggregate(
            total=Sum("amount")
        )["total"]
        return int(total or 0)


class UsageRecord(TenantOwnedModel):
    """Metered usage, recorded whether or not it is billed.

    Kept separate from the credit ledger because the two answer different
    questions: this one is "what did this tenant consume", the ledger is "what
    did they pay for". Reconciling them is how overage billing works later.
    """

    metric = models.CharField(_("metric"), max_length=64, db_index=True)
    quantity = models.BigIntegerField(_("quantity"), default=0)
    unit = models.CharField(_("unit"), max_length=32, blank=True)

    # AI cost attribution (PRD section 59).
    model_name = models.CharField(_("model"), max_length=100, blank=True)
    input_tokens = models.BigIntegerField(_("input tokens"), default=0)
    output_tokens = models.BigIntegerField(_("output tokens"), default=0)
    estimated_cost_minor = models.BigIntegerField(_("estimated cost (minor units)"), default=0)
    currency = models.CharField(_("currency"), max_length=3, default="USD")

    occurred_at = models.DateTimeField(_("occurred at"), db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="usage_records",
    )
    metadata = models.JSONField(_("metadata"), default=dict, blank=True)

    class Meta:
        verbose_name = _("usage record")
        verbose_name_plural = _("usage records")
        ordering = ["-occurred_at", "-id"]
        indexes = [
            models.Index(
                fields=["organization", "metric", "-occurred_at"], name="usage_org_metric_idx"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.metric}={self.quantity} {self.unit}".strip()
