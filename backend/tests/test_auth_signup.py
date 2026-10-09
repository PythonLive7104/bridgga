"""Signup through the headless API (PRD section 23)."""

from __future__ import annotations

from typing import Any

import pytest
from django.contrib.auth import get_user_model

pytestmark = pytest.mark.django_db

SIGNUP_URL = "/auth/browser/v1/auth/signup"
User = get_user_model()


def test_signup_stores_the_name_it_collected(api_client: Any) -> None:
    """The name field is only worth asking for if it is actually kept.

    allauth's SIGNUP_FIELDS does not understand `first_name`, so this goes
    through ACCOUNT_SIGNUP_FORM_CLASS. That the headless endpoint picks the
    form up at all is the thing under test; without it the field would be
    accepted, ignored, and silently lost.
    """
    response = api_client.post(
        SIGNUP_URL,
        {
            "email": "ada@example.test",
            "password": "a-long-enough-passphrase",
            "first_name": "Ada",
            "last_name": "Lovelace",
        },
        format="json",
    )

    assert response.status_code in {200, 401}  # 401: verification pending
    user = User.objects.get(email="ada@example.test")
    assert user.first_name == "Ada"
    assert user.last_name == "Lovelace"


def test_the_name_is_optional(api_client: Any) -> None:
    """A required name buys a nicer greeting at the price of a step."""
    api_client.post(
        SIGNUP_URL,
        {"email": "anon@example.test", "password": "a-long-enough-passphrase"},
        format="json",
    )

    user = User.objects.get(email="anon@example.test")
    assert user.first_name == ""


def test_a_short_password_is_refused(api_client: Any) -> None:
    """The client shows a strength meter; the server is what enforces it."""
    response = api_client.post(
        SIGNUP_URL,
        {"email": "short@example.test", "password": "short"},
        format="json",
    )

    assert response.status_code == 400
    assert not User.objects.filter(email="short@example.test").exists()


def test_an_all_numeric_password_is_refused(api_client: Any) -> None:
    response = api_client.post(
        SIGNUP_URL,
        {"email": "digits@example.test", "password": "19283746501"},
        format="json",
    )

    assert response.status_code == 400
    assert not User.objects.filter(email="digits@example.test").exists()


def test_a_signed_up_user_can_then_sign_in(api_client: Any, settings: Any) -> None:
    """The Phase 1 exit gate, end to end.

    Signup, login and the session cookie were never covered by a test, which
    is how a 500 on every signup attempt survived to Phase 2.
    """
    settings.ACCOUNT_EMAIL_VERIFICATION = "none"

    signup = api_client.post(
        SIGNUP_URL,
        {"email": "grace@example.test", "password": "a-long-enough-passphrase"},
        format="json",
    )
    assert signup.status_code == 200

    # Signup signs you in, so the session has to go before login is testable.
    api_client.delete("/auth/browser/v1/auth/session")
    login = api_client.post(
        "/auth/browser/v1/auth/login",
        {"email": "grace@example.test", "password": "a-long-enough-passphrase"},
        format="json",
    )

    assert login.status_code == 200
    assert login.json()["meta"]["is_authenticated"] is True


def test_signing_up_twice_does_not_confirm_the_address_exists(api_client: Any) -> None:
    """ACCOUNT_PREVENT_ENUMERATION: a signup form is an account oracle otherwise."""
    payload = {"email": "taken@example.test", "password": "a-long-enough-passphrase"}
    first = api_client.post(SIGNUP_URL, payload, format="json")
    second = api_client.post(SIGNUP_URL, payload, format="json")

    assert second.status_code == first.status_code
    assert User.objects.filter(email="taken@example.test").count() == 1


# --------------------------------------------------------------------------- #
# The development-only verify_email command
# --------------------------------------------------------------------------- #


def test_verify_email_command_lets_an_account_sign_in(api_client: Any, settings: Any) -> None:
    from io import StringIO

    from django.core.management import call_command

    # The command refuses to run otherwise, which is the point of the next test.
    settings.DEBUG = True

    api_client.post(
        SIGNUP_URL,
        {"email": "pending@example.test", "password": "a-long-enough-passphrase"},
        format="json",
    )
    api_client.delete("/auth/browser/v1/auth/session")

    call_command("verify_email", "pending@example.test", stdout=StringIO())

    login = api_client.post(
        "/auth/browser/v1/auth/login",
        {"email": "pending@example.test", "password": "a-long-enough-passphrase"},
        format="json",
    )
    assert login.status_code == 200


def test_verify_email_command_refuses_to_run_in_production(settings: Any) -> None:
    """Marking any address verified is account takeover for anyone who knows it."""
    from io import StringIO

    from django.core.management import call_command
    from django.core.management.base import CommandError

    settings.DEBUG = False
    with pytest.raises(CommandError, match="DEBUG"):
        call_command("verify_email", "anyone@example.test", stdout=StringIO())


def test_verify_email_command_rejects_an_unknown_address(settings: Any) -> None:
    from io import StringIO

    from django.core.management import call_command
    from django.core.management.base import CommandError

    settings.DEBUG = True
    with pytest.raises(CommandError, match="No account found"):
        call_command("verify_email", "nobody@example.test", stdout=StringIO())


def test_logging_in_twice_answers_409_with_no_error_body(api_client: Any, settings: Any) -> None:
    """Pins the shape the client has to interpret.

    allauth refuses a second login while a session exists, and the 409 it
    returns carries no `errors` array. A client that assumes one reports
    "Authentication failed" to somebody who is, in fact, signed in -- which is
    what happened. If this response ever grows an error body, the client's
    special case should be revisited rather than silently kept.
    """
    settings.ACCOUNT_EMAIL_VERIFICATION = "none"
    credentials = {"email": "twice@example.test", "password": "a-long-enough-passphrase"}
    api_client.post(SIGNUP_URL, credentials, format="json")

    again = api_client.post("/auth/browser/v1/auth/login", credentials, format="json")

    assert again.status_code == 409
    assert "errors" not in again.json()
