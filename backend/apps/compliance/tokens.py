"""Unsubscribe links (PRD sections 62 and 63).

A signed token carrying who, for which organization, and from which message.

**It never expires.** Every other token in the product has a lifetime; this one
must not. An unsubscribe link in an email sent in March has to work in
November, because the person reading it then is exactly the person most likely
to mark the message as spam if it does not. A link that expires is a dark
pattern with a deliverability cost attached.

**It is signed, not stored.** No row to look up, so an unsubscribe works
even if the campaign, the message or the person record has since been deleted,
and there is no table of tokens to enumerate. The signature is what makes the
link unguessable; the payload is readable by design, since it names only the
address that already received the message.

**One click, really one click.** RFC 8058 requires that the ``List-Unsubscribe``
POST completes the opt-out without a confirmation step, because mailbox
providers test it. The same token serves the one-click POST and the human
landing page.
"""

from __future__ import annotations

from typing import Any

from django.core import signing

#: Changing this invalidates every unsubscribe link ever sent, so it does not
#: change. The salt is namespaced rather than versioned for that reason.
SALT = "bridgga.compliance.unsubscribe"


def make_token(
    *, organization: Any, address: str, message_id: str = "", campaign_id: str = ""
) -> str:
    """Sign an unsubscribe token for one recipient."""
    from apps.compliance.models import normalise_address

    payload = {
        "o": str(organization.public_id),
        "a": normalise_address(address),
    }
    # Only included when known, so the token stays short in the common case
    # and the payload says nothing it does not need to.
    if message_id:
        payload["m"] = str(message_id)
    if campaign_id:
        payload["c"] = str(campaign_id)
    return signing.dumps(payload, salt=SALT, compress=True)


def read_token(token: str) -> dict[str, str] | None:
    """Decode a token, or None if it was not signed by us.

    No ``max_age``: see the module docstring. A tampered or truncated token
    returns None rather than raising, because this is reached from a public
    URL somebody may have mangled by forwarding the email.
    """
    try:
        payload = signing.loads(token, salt=SALT)
    except signing.BadSignature:
        return None

    if not isinstance(payload, dict) or not payload.get("a") or not payload.get("o"):
        return None

    return {
        "organization": str(payload["o"]),
        "address": str(payload["a"]),
        "message": str(payload.get("m", "")),
        "campaign": str(payload.get("c", "")),
    }


def unsubscribe_url(*, token: str, base_url: str = "") -> str:
    """The link that goes in the message footer and the header."""
    from django.conf import settings

    # FRONTEND_URL is already the setting every other customer-facing link
    # is built from (verification, password reset), and an unsubscribe link
    # that pointed somewhere else would be the one link in the product on a
    # different host from the rest.
    root = (base_url or getattr(settings, "FRONTEND_URL", "")).rstrip("/")
    return f"{root}/unsubscribe/{token}"


def list_unsubscribe_headers(*, token: str, base_url: str = "", mailto: str = "") -> dict[str, str]:
    """RFC 8058 headers, which are what mailbox providers actually honour.

    A footer link is for the reader; these are for Gmail's "unsubscribe"
    button. Sending without them is how a message that offers an opt-out still
    gets reported as spam, because the one-click control the reader reached
    for was not there.
    """
    url = unsubscribe_url(token=token, base_url=base_url)
    targets = [f"<{url}>"]
    if mailto:
        targets.insert(0, f"<mailto:{mailto}?subject=unsubscribe>")

    return {
        "List-Unsubscribe": ", ".join(targets),
        # Only valid alongside an HTTPS target, and it is the half that makes
        # the button one click rather than a landing page.
        "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
    }


__all__ = ["SALT", "list_unsubscribe_headers", "make_token", "read_token", "unsubscribe_url"]
