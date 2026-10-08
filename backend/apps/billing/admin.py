from django.contrib import admin

from apps.billing.models import CreditEntry, Plan, Subscription, UsageRecord
from apps.common.admin import ReadOnlyModelAdmin, UnscopedModelAdmin


@admin.register(Plan)
class PlanAdmin(UnscopedModelAdmin):
    list_display = (
        "name",
        "tier",
        "monthly_price_minor",
        "currency",
        "included_credits",
        "is_public",
    )
    list_filter = ("tier", "is_public", "currency")
    search_fields = ("name",)


@admin.register(Subscription)
class SubscriptionAdmin(UnscopedModelAdmin):
    list_display = ("organization", "plan", "status", "seats", "current_period_end")
    list_filter = ("status", "provider", "plan")
    search_fields = ("organization__name", "provider_customer_id")


@admin.register(CreditEntry)
class CreditEntryAdmin(ReadOnlyModelAdmin):
    """Append-only ledger: editing a past entry would break reconciliation."""

    list_display = ("created_at", "organization", "amount", "reason", "feature")
    list_filter = ("reason",)
    search_fields = ("organization__name", "description", "reference")
    date_hierarchy = "created_at"


@admin.register(UsageRecord)
class UsageRecordAdmin(ReadOnlyModelAdmin):
    list_display = ("occurred_at", "organization", "metric", "quantity", "model_name")
    list_filter = ("metric",)
    search_fields = ("organization__name", "metric")
    date_hierarchy = "occurred_at"
