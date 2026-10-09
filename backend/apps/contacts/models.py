"""People at prospect companies (PRD sections 31, 60, 61, 80).

This is the model that holds personal data, so it is the one with the most
rules attached. Three shape it:

* **Section 60** requires a status, a verification date, a source and a
  confidence *per contact channel* -- not per record. An address that bounced
  and a phone number nobody has checked are different facts about the same
  person, and one status field cannot carry both.
* **Section 62** permits public business contact details only, and requires
  legal review before enrichment at scale. Nothing here invites a personal
  address.
* **Section 63** makes an opt-out a compliance obligation rather than a
  preference, so ``can_be_contacted`` consults the status rather than leaving
  each caller to remember which values mean "stop".
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import (
    UNSENDABLE_CONTACT_STATUSES,
    ContactStatus,
    ProvenancedModel,
    TenantOwnedModel,
)


class Seniority(models.TextChoices):
    """Coarse bands, because titles do not translate between companies.

    A "Head of Growth" at a twenty-person company and at a bank are different
    jobs, and matching on the title string finds neither reliably.
    """

    INDIVIDUAL = "individual", _("Individual contributor")
    MANAGER = "manager", _("Manager")
    DIRECTOR = "director", _("Director")
    VP = "vp", _("VP")
    C_LEVEL = "c_level", _("C-level")
    FOUNDER = "founder", _("Founder / Owner")


class Person(TenantOwnedModel, ProvenancedModel):
    """A person at a prospect company."""

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="people",
        verbose_name=_("company"),
    )

    first_name = models.CharField(_("first name"), max_length=150, blank=True)
    last_name = models.CharField(_("last name"), max_length=150, blank=True)
    full_name = models.CharField(_("full name"), max_length=300, blank=True)

    job_title = models.CharField(_("job title"), max_length=200, blank=True)
    department = models.CharField(_("department"), max_length=120, blank=True)
    seniority = models.CharField(
        _("seniority"), max_length=16, choices=Seniority.choices, blank=True
    )
    is_decision_maker = models.BooleanField(_("decision maker"), default=False)

    linkedin_url = models.URLField(_("LinkedIn"), max_length=500, blank=True)
    country = models.CharField(_("country"), max_length=2, blank=True)
    city = models.CharField(_("city"), max_length=120, blank=True)

    # --- Email, with its own quality record (section 60) ------------------- #
    email = models.EmailField(_("email"), max_length=254, blank=True, db_index=True)
    email_status = models.CharField(
        _("email status"),
        max_length=16,
        choices=ContactStatus.choices,
        default=ContactStatus.UNKNOWN,
        db_index=True,
    )
    email_verified_at = models.DateTimeField(_("email verified at"), null=True, blank=True)
    email_source = models.CharField(_("email source"), max_length=100, blank=True)

    # --- Phone, likewise --------------------------------------------------- #
    phone = models.CharField(_("phone"), max_length=40, blank=True)
    phone_status = models.CharField(
        _("phone status"),
        max_length=16,
        choices=ContactStatus.choices,
        default=ContactStatus.UNKNOWN,
    )
    phone_verified_at = models.DateTimeField(_("phone verified at"), null=True, blank=True)
    phone_source = models.CharField(_("phone source"), max_length=100, blank=True)

    last_seen_at = models.DateTimeField(_("last seen"), null=True, blank=True)
    metadata = models.JSONField(_("metadata"), default=dict, blank=True)

    class Meta:
        verbose_name = _("person")
        verbose_name_plural = _("people")
        ordering = ["last_name", "first_name", "id"]
        constraints = [
            # Partial: a person without an email is still a person worth
            # keeping, and without the condition they would all collide.
            models.UniqueConstraint(
                fields=["organization", "email"],
                condition=~models.Q(email=""),
                name="one_person_per_email_per_org",
            )
        ]
        indexes = [
            models.Index(fields=["organization", "company"], name="person_org_company_idx"),
            models.Index(
                fields=["organization", "email_status"], name="person_org_emailstatus_idx"
            ),
        ]

    def __str__(self) -> str:
        return self.display_name

    def save(self, *args: object, **kwargs: object) -> None:
        self.email = (self.email or "").strip().lower()
        if not self.full_name:
            self.full_name = " ".join(filter(None, [self.first_name, self.last_name])).strip()
        super().save(*args, **kwargs)  # type: ignore[arg-type]

    @property
    def display_name(self) -> str:
        return self.full_name or self.email or str(self.public_id)

    @property
    def can_be_emailed(self) -> bool:
        """Whether this address may be sent to at all.

        A single place to ask, because the alternative is each caller
        remembering which of six statuses mean stop -- and the cost of
        forgetting is a message to someone who unsubscribed, which section 63
        treats as a compliance failure rather than a bug.

        This is a necessary condition, never a sufficient one. The send path
        must still check the suppression list, which is organization-wide and
        outlives any individual record.
        """
        if not self.email:
            return False
        return self.email_status not in UNSENDABLE_CONTACT_STATUSES

    def mark_bounced(self) -> None:
        """Record a hard bounce. Called from provider webhooks in Phase 3."""
        from django.utils import timezone

        self.email_status = ContactStatus.BOUNCED
        self.email_verified_at = timezone.now()
        self.save(update_fields=["email_status", "email_verified_at", "updated_at"])

    def mark_unsubscribed(self) -> None:
        """Record an opt-out on this record.

        Not the whole story: an opt-out is global to the organization and must
        also reach the suppression list, or the same person is reachable again
        through a second record. This marks the record; the service layer owns
        the rest.
        """
        from django.utils import timezone

        self.email_status = ContactStatus.UNSUBSCRIBED
        self.email_verified_at = timezone.now()
        self.save(update_fields=["email_status", "email_verified_at", "updated_at"])
