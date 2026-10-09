"""Seed or refresh the country profiles.

    python manage.py seed_countries

Idempotent, and safe to re-run after the seed data changes. Fields a customer
cannot edit are updated in place; nothing is deleted, because a country row is
referenced by every recommendation made against it.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.intelligence.country_seed import all_seed_countries
from apps.intelligence.models import CountryProfile


class Command(BaseCommand):
    help = "Create or update the seeded country profiles (PRD sections 30, 71)."

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        created = updated = 0

        for entry in all_seed_countries():
            code = entry.pop("code")
            _, was_created = CountryProfile.objects.update_or_create(code=code, defaults=entry)
            created += was_created
            updated += not was_created

        self.stdout.write(
            self.style.SUCCESS(f"Countries seeded: {created} created, {updated} updated.")
        )
