"""Extra fields collected at signup.

allauth's ``SIGNUP_FIELDS`` setting only understands the identifiers it ships
with -- email, username, password. Anything else goes through
``ACCOUNT_SIGNUP_FORM_CLASS``, which ``BaseSignupForm`` inherits from and which
the headless ``SignupInput`` therefore picks up too. So one form serves both
the HTML flow and the JSON API, and the fields are genuinely persisted rather
than collected and dropped.
"""

from __future__ import annotations

from typing import Any

from django import forms
from django.utils.translation import gettext_lazy as _


class SignupForm(forms.Form):
    """Collects the person's name alongside their credentials.

    Optional, deliberately. A required name field buys a slightly nicer
    greeting at the cost of a step between someone and the product, and an
    invented "N/A" in the database when they do not want to give it. The name
    is also editable later from settings.
    """

    first_name = forms.CharField(
        label=_("First name"),
        max_length=150,
        required=False,
        strip=True,
    )
    last_name = forms.CharField(
        label=_("Last name"),
        max_length=150,
        required=False,
        strip=True,
    )

    def signup(self, request: Any, user: Any) -> None:
        """Called by allauth once the user row exists."""
        user.first_name = self.cleaned_data.get("first_name", "")
        user.last_name = self.cleaned_data.get("last_name", "")
        user.save(update_fields=["first_name", "last_name"])
