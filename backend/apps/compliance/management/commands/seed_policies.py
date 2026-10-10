"""Write the regional policy table (PRD section 62).

    python manage.py seed_policies

Idempotent, so it belongs in the deploy. The values are a conservative
starting point for a legal review, not the review -- see
``apps.compliance.policy_seed``.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from apps.compliance.policy_seed import seed_policies


class Command(BaseCommand):
    help = "Seed the regional compliance policies."

    def handle(self, *args: Any, **options: Any) -> None:
        result = seed_policies()
        self.stdout.write(
            self.style.SUCCESS(
                f"Policies: {result['created']} created, {result['updated']} updated."
            )
        )
