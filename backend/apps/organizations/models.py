"""Organization, Workspace, Membership, Invitation (PRD section 24)."""

from __future__ import annotations

import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from apps.common.models import BaseModel, TenantOwnedModel
from apps.organizations.roles import Capability, Role, capabilities_for

INVITATION_TTL = timedelta(days=7)


class Organization(BaseModel):
    """The tenant root. Every tenant-owned row ultimately points here.

    Deliberately not a ``TenantOwnedModel``: it is the tenant, so it cannot be
    scoped by one. Access is mediated by ``Membership`` instead.
    """

    name = models.CharField(_("name"), max_length=200)
    slug = models.SlugField(_("slug"), max_length=220, unique=True)

    # Africa-first defaults (PRD sections 71 and 72): a Lagos team should not
    # have to reconfigure currency and timezone before doing anything.
    country = models.CharField(_("country"), max_length=2, blank=True)
    default_currency = models.CharField(_("default currency"), max_length=3, default="USD")
    timezone = models.CharField(_("timezone"), max_length=64, default="UTC")

    website = models.URLField(_("website"), blank=True)
    is_active = models.BooleanField(_("active"), default=True)

    #: When this organization finished the section 25 path. The *progress*
    #: through onboarding is derived from the records themselves
    #: (apps.organizations.onboarding) rather than stored, because a counter
    #: drifts the moment somebody deletes the thing it was counting. This one
    #: timestamp is genuinely a decision and not a derivation: once a customer
    #: has been through, deleting an ICP later should not drag them back
    #: through an introduction they have already had.
    onboarding_completed_at = models.DateTimeField(
        _("onboarding completed at"), null=True, blank=True
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="organizations_created",
    )

    class Meta:
        verbose_name = _("organization")
        verbose_name_plural = _("organizations")
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args: object, **kwargs: object) -> None:
        if not self.slug:
            self.slug = self._unique_slug(self.name)
        super().save(*args, **kwargs)  # type: ignore[arg-type]

    @staticmethod
    def _unique_slug(name: str) -> str:
        base = slugify(name)[:200] or "org"
        candidate = base
        suffix = 0
        while Organization.objects.filter(slug=candidate).exists():
            suffix += 1
            candidate = f"{base}-{suffix}"
        return candidate

    def membership_for(self, user: object) -> Membership | None:
        if not getattr(user, "is_authenticated", False):
            return None
        return (
            Membership.all_objects.filter(organization=self, user=user, is_active=True)
            .select_related("organization")
            .first()
        )


class Workspace(TenantOwnedModel):
    """A sub-account inside an organization (Main Sales, Nigeria, Kenya...)."""

    name = models.CharField(_("name"), max_length=200)
    slug = models.SlugField(_("slug"), max_length=220)
    is_default = models.BooleanField(_("default"), default=False)

    # Per-workspace market focus: an agency running Nigeria and Kenya from one
    # organization needs these to differ.
    country = models.CharField(_("country"), max_length=2, blank=True)
    timezone = models.CharField(_("timezone"), max_length=64, blank=True)

    class Meta:
        verbose_name = _("workspace")
        verbose_name_plural = _("workspaces")
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "slug"], name="workspace_slug_unique_per_org"
            ),
            # At most one default workspace per organization.
            models.UniqueConstraint(
                fields=["organization"],
                condition=models.Q(is_default=True),
                name="workspace_single_default_per_org",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    def save(self, *args: object, **kwargs: object) -> None:
        if not self.slug:
            self.slug = slugify(self.name)[:200] or "workspace"
        super().save(*args, **kwargs)  # type: ignore[arg-type]


class Membership(TenantOwnedModel):
    """Joins a user to an organization with exactly one role."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    role = models.CharField(_("role"), max_length=32, choices=Role.choices, default=Role.VIEWER)
    is_active = models.BooleanField(_("active"), default=True)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="memberships_invited",
    )
    joined_at = models.DateTimeField(_("joined at"), default=timezone.now)

    class Meta:
        verbose_name = _("membership")
        verbose_name_plural = _("memberships")
        ordering = ["user__email"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "user"], name="membership_unique_per_org"
            )
        ]

    def __str__(self) -> str:
        return f"{self.user} @ {self.organization} ({self.role})"

    @property
    def capabilities(self) -> frozenset[str]:
        return capabilities_for(self.role)

    def has_capability(self, capability: str) -> bool:
        return self.is_active and capability in self.capabilities


class Invitation(TenantOwnedModel):
    """A pending invitation to join an organization.

    Only a hash of the token is stored, so a database dump does not hand an
    attacker working invitation links.
    """

    email = models.EmailField(_("email"))
    role = models.CharField(_("role"), max_length=32, choices=Role.choices, default=Role.VIEWER)
    token_hash = models.CharField(_("token hash"), max_length=128, unique=True)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invitations_sent",
    )
    expires_at = models.DateTimeField(_("expires at"))
    accepted_at = models.DateTimeField(_("accepted at"), null=True, blank=True)
    revoked_at = models.DateTimeField(_("revoked at"), null=True, blank=True)

    class Meta:
        verbose_name = _("invitation")
        verbose_name_plural = _("invitations")
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "email"],
                condition=models.Q(accepted_at__isnull=True, revoked_at__isnull=True),
                name="invitation_one_pending_per_email_per_org",
            )
        ]

    def __str__(self) -> str:
        return f"invite {self.email} -> {self.organization}"

    @property
    def is_pending(self) -> bool:
        return (
            self.accepted_at is None
            and self.revoked_at is None
            and self.expires_at > timezone.now()
        )

    @staticmethod
    def hash_token(raw_token: str) -> str:
        from django.utils.crypto import salted_hmac

        # Keyed hash, so a stolen database cannot be brute-forced offline
        # without also stealing SECRET_KEY.
        return salted_hmac("bridgga.invitation", raw_token).hexdigest()

    @classmethod
    def issue(
        cls,
        *,
        organization: Organization,
        email: str,
        role: str,
        invited_by: object | None = None,
    ) -> tuple[Invitation, str]:
        """Create an invitation and return it with its one-time raw token."""
        raw_token = secrets.token_urlsafe(32)
        invitation = cls.objects.create(
            organization=organization,
            email=email.lower().strip(),
            role=role,
            token_hash=cls.hash_token(raw_token),
            invited_by=invited_by if getattr(invited_by, "pk", None) else None,
            expires_at=timezone.now() + INVITATION_TTL,
        )
        return invitation, raw_token


__all__ = [
    "Capability",
    "Invitation",
    "Membership",
    "Organization",
    "Role",
    "Workspace",
]
