"""Suppression, consent and regional policy (PRD sections 62 and 63).

This is built before anything can send, which is the order the build plan
insists on and the only order that works: a suppression list added after the
first campaign is a suppression list with a gap in it, and the gap is a person
who asked not to be contacted.

Three decisions shape these models.

**Matching is by hash, so erasure and suppression can both be honoured.**
Section 63 ends with a requirement that reads like a contradiction: suppress
the person, and "preserve minimum data necessary to honor suppression
obligations". If somebody asks to be deleted and we delete the address, we
lose the ability to recognise them and will contact them again. Storing a
``sha256`` of the normalised address as the matching key resolves it: the
plaintext can be redacted on request while the entry still matches. The hash
is what the send path looks at; the plaintext is only ever for display.

**Suppression is organization-wide, never cross-tenant.** "Stop contacting me"
is said to a sender, not to a platform. One customer's unsubscribe must
suppress that person across every campaign, workspace and channel that
customer runs -- and must not touch a different customer with their own
relationship to the same person.

**Unknown regions fail closed.** ``policy_for`` returns the strict default
when it does not recognise a country, so a market nobody has configured
behaves as though prior consent is required rather than as though anything
goes.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.common.models import BaseModel, TenantOwnedModel

_ANGLE_ADDRESS = re.compile(r"<([^>]+)>")


def normalise_address(value: str) -> str:
    """Reduce an address to the form two records are compared on.

    Lowercased, trimmed, and unwrapped from a display name, because
    ``"Ada Obi" <ADA@Example.com>`` and ``ada@example.com`` are one person and
    a suppression list that holds both as separate rows will honour neither
    reliably.

    Deliberately *not* clever about provider-specific aliasing: Gmail ignores
    dots and everything after a ``+``, and most providers do not. Normalising
    for one vendor's rules would silently suppress addresses nobody asked to
    suppress on every other vendor.
    """
    candidate = (value or "").strip()
    match = _ANGLE_ADDRESS.search(candidate)
    if match:
        candidate = match.group(1)
    return candidate.strip().lower()


def address_hash(value: str) -> str:
    """The matching key. See the module docstring for why it is a hash."""
    return hashlib.sha256(normalise_address(value).encode("utf-8")).hexdigest()


def domain_of(value: str) -> str:
    address = normalise_address(value)
    return address.rsplit("@", 1)[-1] if "@" in address else ""


class SuppressionKind(models.TextChoices):
    EMAIL = "email", _("Email address")
    PHONE = "phone", _("Phone number")
    #: A whole company asking to be left alone. One request, one row, every
    #: address at that domain covered -- including ones not yet discovered.
    DOMAIN = "domain", _("Domain")


class SuppressionScope(models.TextChoices):
    ALL = "all", _("Every channel")
    EMAIL = "email", _("Email")
    SMS = "sms", _("SMS")
    WHATSAPP = "whatsapp", _("WhatsApp")
    CALL = "call", _("Calls")


class SuppressionReason(models.TextChoices):
    UNSUBSCRIBED = "unsubscribed", _("Unsubscribed")
    COMPLAINED = "complained", _("Marked as spam")
    BOUNCED = "bounced", _("Hard bounce")
    MANUAL = "manual", _("Added by hand")
    IMPORTED = "imported", _("Imported suppression list")
    LEGAL_REQUEST = "legal_request", _("Legal or erasure request")


#: Reasons that record somebody's own decision. These can never be removed:
#: see ``SuppressionEntry.is_removable``.
PERMANENT_REASONS = frozenset(
    {
        SuppressionReason.UNSUBSCRIBED,
        SuppressionReason.COMPLAINED,
        SuppressionReason.LEGAL_REQUEST,
    }
)


class SuppressionEntry(TenantOwnedModel):
    """One person, or one domain, that this customer must not contact."""

    kind = models.CharField(
        _("kind"), max_length=10, choices=SuppressionKind.choices, default=SuppressionKind.EMAIL
    )
    #: What the send path matches on. Indexed, and never null.
    value_hash = models.CharField(_("value hash"), max_length=64, db_index=True)
    #: The readable form, kept for the customer's own suppression list and
    #: redacted on an erasure request. Never used for matching.
    value = models.CharField(_("value"), max_length=320, blank=True)

    scope = models.CharField(
        _("scope"), max_length=10, choices=SuppressionScope.choices, default=SuppressionScope.ALL
    )
    reason = models.CharField(
        _("reason"),
        max_length=20,
        choices=SuppressionReason.choices,
        default=SuppressionReason.UNSUBSCRIBED,
    )
    source = models.CharField(
        _("source"),
        max_length=120,
        blank=True,
        help_text=_("Where it came from: unsubscribe_link, webhook:ses, import, api."),
    )
    notes = models.CharField(_("notes"), max_length=255, blank=True)

    #: Section 63: "record timestamp". Separate from created_at because an
    #: imported list carries the date the person actually opted out, which is
    #: the date that matters if anybody asks.
    suppressed_at = models.DateTimeField(_("suppressed at"), default=timezone.now, db_index=True)

    person = models.ForeignKey(
        "contacts.Person",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="suppressions",
        verbose_name=_("person"),
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="suppressions_created",
        verbose_name=_("added by"),
    )
    #: What the person was reacting to, where it is known: the campaign, the
    #: message, the webhook payload id. The answer to "why is this person on
    #: the list?" six months later.
    evidence = models.JSONField(_("evidence"), default=dict, blank=True)
    redacted_at = models.DateTimeField(_("redacted at"), null=True, blank=True)

    class Meta:
        verbose_name = _("suppression entry")
        verbose_name_plural = _("suppression entries")
        ordering = ["-suppressed_at", "-id"]
        constraints = [
            # One row per address per scope. Without it, a person who
            # unsubscribes twice is on the list twice and every report about
            # the list is wrong.
            models.UniqueConstraint(
                fields=["organization", "kind", "value_hash", "scope"],
                name="one_suppression_per_value_and_scope",
            )
        ]
        indexes = [
            # The send-path query, which runs per recipient: this
            # organization, this hash, these scopes.
            models.Index(
                fields=["organization", "value_hash", "scope"], name="supp_org_hash_scope_idx"
            ),
            models.Index(fields=["organization", "reason"], name="supp_org_reason_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.value or self.value_hash[:12]} ({self.reason})"

    @property
    def is_removable(self) -> bool:
        """Whether this entry may be deleted.

        A mistyped manual entry is a mistake to correct. An unsubscribe, a
        spam complaint or an erasure request is somebody's decision, and a
        product that lets an operator delete it has built a button whose only
        use is to contact a person who said stop.
        """
        return self.reason not in PERMANENT_REASONS

    @property
    def is_redacted(self) -> bool:
        return self.redacted_at is not None

    def masked_value(self) -> str:
        """``ada@example.com`` as ``a***@example.com``.

        For the unsubscribe confirmation page, which is shown to whoever holds
        the link: enough to confirm the right address without printing it to
        anybody who guessed or intercepted the URL.
        """
        if not self.value or "@" not in self.value:
            return ""
        local, _, domain = self.value.partition("@")
        return f"{local[:1]}***@{domain}"


class ConsentBasis(models.TextChoices):
    """Why this customer believes they may contact this person.

    Named after the lawful bases the regimes in section 62 share. Recording
    which one applies is the difference between a defensible position and a
    hopeful one.
    """

    CONSENT = "consent", _("They opted in")
    LEGITIMATE_INTEREST = "legitimate_interest", _("Legitimate interest (B2B)")
    CONTRACT = "contract", _("Existing contract or relationship")
    PUBLIC_RECORD = "public_record", _("Published business contact details")


class ConsentRecord(TenantOwnedModel):
    """What this customer relies on to contact one person (PRD section 62)."""

    person = models.ForeignKey(
        "contacts.Person",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="consent_records",
        verbose_name=_("person"),
    )
    value_hash = models.CharField(_("address hash"), max_length=64, db_index=True)
    value = models.CharField(_("address"), max_length=320, blank=True)

    basis = models.CharField(_("basis"), max_length=24, choices=ConsentBasis.choices)
    source = models.CharField(_("source"), max_length=200, blank=True)
    evidence = models.TextField(
        _("evidence"),
        blank=True,
        help_text=_("What would be shown if asked: the form, the page, the contract."),
    )
    country = models.CharField(_("country"), max_length=2, blank=True)

    captured_at = models.DateTimeField(_("captured at"), default=timezone.now)
    #: Consent withdrawn is not consent deleted: the record that it once
    #: existed, and when it ended, is the part that matters afterwards.
    withdrawn_at = models.DateTimeField(_("withdrawn at"), null=True, blank=True)

    class Meta:
        verbose_name = _("consent record")
        verbose_name_plural = _("consent records")
        ordering = ["-captured_at", "-id"]
        indexes = [
            models.Index(fields=["organization", "value_hash"], name="consent_org_hash_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.value or self.value_hash[:12]}: {self.basis}"

    @property
    def is_active(self) -> bool:
        return self.withdrawn_at is None


class RegionalPolicy(BaseModel):
    """What one market requires (PRD section 62).

    Platform-level reference data, like ``CountryProfile``: the rules of
    Nigeria are the same for every customer. Which markets a customer operates
    in is their data; what those markets demand is not.
    """

    code = models.CharField(_("code"), max_length=5, unique=True)
    name = models.CharField(_("name"), max_length=100)
    law = models.CharField(_("data protection law"), max_length=200, blank=True)

    #: The question that decides whether cold outbound is lawful at all here.
    b2b_requires_prior_consent = models.BooleanField(
        _("B2B email needs prior consent"), default=True
    )
    opt_out_required = models.BooleanField(_("every message needs an opt-out"), default=True)
    #: Most regimes require the sender to be identifiable, several require a
    #: postal address. Both end up in the message footer.
    sender_identity_required = models.BooleanField(_("sender must be identified"), default=True)
    postal_address_required = models.BooleanField(_("postal address in footer"), default=False)

    opt_out_honoured_within_days = models.PositiveSmallIntegerField(
        _("opt-out honoured within (days)"), default=0
    )
    max_retention_days = models.PositiveIntegerField(_("retention limit (days)"), default=0)
    notes = models.TextField(_("notes"), blank=True)

    class Meta:
        verbose_name = _("regional policy")
        verbose_name_plural = _("regional policies")
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"

    def requirements(self) -> list[str]:
        """What a campaign in this market must do, in words a customer reads."""
        items: list[str] = []
        if self.b2b_requires_prior_consent:
            items.append("Prior consent is required before emailing a business contact.")
        if self.opt_out_required:
            items.append("Every message must carry a working opt-out.")
        if self.sender_identity_required:
            items.append("The sender must be clearly identified.")
        if self.postal_address_required:
            items.append("A physical postal address must appear in the message.")
        if self.opt_out_honoured_within_days:
            items.append(
                f"Opt-outs must be honoured within {self.opt_out_honoured_within_days} days."
            )
        if self.max_retention_days:
            items.append(f"Personal data may be kept for {self.max_retention_days} days.")
        return items


def policy_for(code: str) -> Any:
    """The policy for a country, or the strict default.

    **Fails closed.** A market nobody has configured is treated as one that
    requires prior consent, because the alternative is that forgetting to add
    a country silently permits cold outbound into it.
    """
    policy = RegionalPolicy.objects.filter(code=(code or "").upper()).first()
    if policy is not None:
        return policy
    return RegionalPolicy(
        code=(code or "??").upper()[:5],
        name="Unconfigured market",
        law="Unknown",
        b2b_requires_prior_consent=True,
        opt_out_required=True,
        sender_identity_required=True,
        postal_address_required=True,
        notes=(
            "No policy is configured for this market, so the strictest "
            "assumptions apply until one is added."
        ),
    )


__all__ = [
    "PERMANENT_REASONS",
    "ConsentBasis",
    "ConsentRecord",
    "RegionalPolicy",
    "SuppressionEntry",
    "SuppressionKind",
    "SuppressionReason",
    "SuppressionScope",
    "address_hash",
    "domain_of",
    "normalise_address",
    "policy_for",
]
