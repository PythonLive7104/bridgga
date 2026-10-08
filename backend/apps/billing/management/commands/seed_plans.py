"""Seed the plan catalogue.

Idempotent: safe to run on every deploy. Prices here are placeholders -- PRD
section 68 is explicit that pricing must be validated with real customers
rather than assumed, so these exist to make the free tier work, not to set
commercial terms.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from apps.billing.models import Plan, PlanTier

PLANS: list[dict[str, Any]] = [
    {
        "tier": PlanTier.FREE,
        "name": "Free",
        "description": "Limited prospect discovery, AI research and campaigns.",
        "monthly_price_minor": 0,
        "included_credits": 50,
        "max_seats": 2,
        "max_workspaces": 1,
        "max_prospects_per_month": 50,
        "sort_order": 0,
    },
    {
        "tier": PlanTier.STARTER,
        "name": "Starter",
        "description": "For early startups finding their first customers.",
        "monthly_price_minor": 4900,
        "included_credits": 500,
        "max_seats": 3,
        "max_workspaces": 2,
        "max_prospects_per_month": 1000,
        "sort_order": 1,
    },
    {
        "tier": PlanTier.GROWTH,
        "name": "Growth",
        "description": "For teams running repeatable acquisition.",
        "monthly_price_minor": 14900,
        "included_credits": 2500,
        "max_seats": 10,
        "max_workspaces": 5,
        "max_prospects_per_month": 10000,
        "sort_order": 2,
    },
    {
        "tier": PlanTier.AGENCY,
        "name": "Agency",
        "description": "Multi-client workspaces and client reporting.",
        "monthly_price_minor": 39900,
        "included_credits": 8000,
        "max_seats": 25,
        "max_workspaces": 25,
        "max_prospects_per_month": 50000,
        "sort_order": 3,
    },
    {
        "tier": PlanTier.ENTERPRISE,
        "name": "Enterprise",
        "description": "Custom limits, security review, API and support.",
        "monthly_price_minor": 0,
        "included_credits": 0,
        "max_seats": None,
        "max_workspaces": None,
        "max_prospects_per_month": None,
        "is_public": False,
        "sort_order": 4,
    },
]


class Command(BaseCommand):
    help = "Create or update the plan catalogue."

    def handle(self, *args: Any, **options: Any) -> None:
        created_count = 0
        updated_count = 0
        for spec in PLANS:
            defaults = {key: value for key, value in spec.items() if key != "tier"}
            _, created = Plan.objects.update_or_create(tier=spec["tier"], defaults=defaults)
            if created:
                created_count += 1
            else:
                updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(f"Plans seeded: {created_count} created, {updated_count} updated.")
        )
