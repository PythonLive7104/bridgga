"""Confirm an email address without the email.

    python manage.py verify_email someone@example.com

Account verification is mandatory (PRD section 23), so until a real mail
provider is configured there is no way through the front door: the account
exists, the link is in a log or a MailHog nobody has opened, and sign-in is
refused. This marks the address verified directly.

Development only -- it refuses to run with DEBUG off, because an operator who
can mark any address verified can take over any account whose address they
know.
"""

from __future__ import annotations

from typing import Any

from allauth.account.models import EmailAddress
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Mark an email address verified, for local development."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("email", help="The address to confirm.")

    def handle(self, *args: Any, **options: Any) -> None:
        if not settings.DEBUG:
            raise CommandError(
                "Refusing to run with DEBUG off. Marking an address verified is "
                "account takeover for anyone who knows it."
            )

        email = options["email"].strip().lower()
        user = get_user_model().objects.filter(email__iexact=email).first()
        if user is None:
            raise CommandError(f"No account found for {email}.")

        address, _ = EmailAddress.objects.get_or_create(
            user=user, email=user.email, defaults={"primary": True}
        )
        if address.verified:
            self.stdout.write(f"{email} was already verified.")
            return

        address.verified = True
        address.primary = True
        address.save(update_fields=["verified", "primary"])
        self.stdout.write(self.style.SUCCESS(f"{email} is verified. You can sign in."))
