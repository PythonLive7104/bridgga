"""Organization service layer.

Business logic lives here rather than in serializers or views (PRD section 79),
so the same operation can be driven by the API, a management command, a Celery
task or a test without duplicating the rules.
"""

from __future__ import annotations

from typing import Any

import structlog
from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditAction
from apps.audit.services import record_audit
from apps.common.tenancy import tenant_context, unscoped
from apps.organizations.models import Invitation, Membership, Organization, Workspace
from apps.organizations.roles import Role, can_assign_role, can_manage_member

logger = structlog.get_logger(__name__)


class OrganizationError(Exception):
    """Domain error with a message safe to show the user."""


def _assert_another_owner_remains(membership: Membership) -> None:
    """Refuse to leave an organization with no owner.

    An ownerless organization cannot change its own billing, roles or
    settings, so recovering one needs staff intervention. Cheaper to prevent.
    """
    remaining = (
        Membership.all_objects.filter(
            organization_id=membership.organization_id,
            role=Role.OWNER,
            is_active=True,
        )
        .exclude(pk=membership.pk)
        .count()
    )
    if remaining == 0:
        raise OrganizationError("An organization must keep at least one owner.")


@transaction.atomic
def create_organization(
    *,
    name: str,
    owner: Any,
    country: str = "",
    default_currency: str = "USD",
    timezone_name: str = "UTC",
    website: str = "",
    request: Any = None,
) -> Organization:
    """Create an organization with its owner, default workspace and trial.

    All four happen together or not at all: an organization without an owner is
    unreachable, and one without a workspace breaks every workspace-scoped
    feature added later.
    """
    name = (name or "").strip()
    if not name:
        raise OrganizationError("Organization name is required.")

    # Creating the tenant necessarily happens outside any tenant scope.
    with unscoped():
        organization = Organization.objects.create(
            name=name,
            country=(country or "").upper()[:2],
            default_currency=(default_currency or "USD").upper()[:3],
            timezone=timezone_name or "UTC",
            website=website or "",
            created_by=owner,
        )

    with tenant_context(organization=organization):
        Membership.objects.create(
            organization=organization,
            user=owner,
            role=Role.OWNER,
            joined_at=timezone.now(),
        )
        Workspace.objects.create(
            organization=organization,
            name="Main Sales",
            slug="main-sales",
            is_default=True,
            country=organization.country,
            timezone=organization.timezone,
        )
        _start_trial(organization)

        record_audit(
            organization=organization,
            action=AuditAction.ORGANIZATION_CREATED,
            actor=owner,
            target=organization,
            metadata={"name": organization.name, "country": organization.country},
            request=request,
        )

    logger.info(
        "organization_created",
        organization_id=str(organization.public_id),
        country=organization.country,
    )
    return organization


def _start_trial(organization: Organization) -> None:
    """Attach the free plan if one has been seeded.

    Absence is not fatal: a fresh database has no plans until the seed command
    runs, and signup must not fail because of it.
    """
    from apps.billing.models import (
        CreditEntry,
        CreditEntryReason,
        Plan,
        PlanTier,
        Subscription,
        SubscriptionStatus,
    )

    plan = Plan.objects.filter(tier=PlanTier.FREE).first()
    if plan is None:
        logger.warning("free_plan_missing", organization_id=str(organization.public_id))
        return

    Subscription.objects.create(
        organization=organization,
        plan=plan,
        status=SubscriptionStatus.TRIALING,
        currency=organization.default_currency,
        seats=1,
    )
    if plan.included_credits:
        CreditEntry.objects.create(
            organization=organization,
            amount=plan.included_credits,
            reason=CreditEntryReason.PLAN_ALLOWANCE,
            description=f"{plan.name} starting allowance",
        )


@transaction.atomic
def invite_member(
    *,
    organization: Organization,
    inviter_membership: Membership,
    email: str,
    role: str,
    request: Any = None,
) -> tuple[Invitation, str]:
    """Invite someone to the organization.

    Returns the invitation and its raw token. The caller is responsible for
    delivering the token; it is never stored in plaintext.
    """
    email = (email or "").strip().lower()
    if not email:
        raise OrganizationError("Email is required.")

    if not can_assign_role(inviter_membership.role, role):
        # Blocks an Admin minting an Owner, and anyone granting their own level.
        raise OrganizationError("You cannot grant a role at or above your own.")

    if Membership.objects.filter(organization=organization, user__email=email).exists():
        raise OrganizationError("That person is already a member of this organization.")

    existing = Invitation.objects.filter(
        organization=organization, email=email, accepted_at__isnull=True, revoked_at__isnull=True
    ).first()
    if existing is not None and existing.is_pending:
        raise OrganizationError("An invitation is already pending for that email.")
    if existing is not None:
        # Expired: clear it so the partial unique constraint allows a new one.
        existing.revoked_at = timezone.now()
        existing.save(update_fields=["revoked_at", "updated_at"])

    invitation, raw_token = Invitation.issue(
        organization=organization,
        email=email,
        role=role,
        invited_by=inviter_membership.user,
    )

    record_audit(
        organization=organization,
        action=AuditAction.MEMBER_INVITED,
        actor=inviter_membership.user,
        target=invitation,
        metadata={"email": email, "role": role},
        request=request,
    )
    return invitation, raw_token


@transaction.atomic
def accept_invitation(*, raw_token: str, user: Any, request: Any = None) -> Membership:
    """Redeem an invitation token for the authenticated user."""
    token_hash = Invitation.hash_token(raw_token or "")

    with unscoped():
        invitation = (
            Invitation.all_objects.select_for_update()
            .select_related("organization")
            .filter(token_hash=token_hash)
            .first()
        )

    if invitation is None or not invitation.is_pending:
        # One message for every failure mode: a distinct "expired" response
        # would confirm that a guessed token was once valid.
        raise OrganizationError("This invitation link is invalid or has expired.")

    if invitation.email != (user.email or "").lower():
        raise OrganizationError("This invitation was issued to a different email address.")

    organization = invitation.organization
    with tenant_context(organization=organization):
        membership, created = Membership.objects.get_or_create(
            organization=organization,
            user=user,
            defaults={"role": invitation.role, "invited_by": invitation.invited_by},
        )
        if not created and not membership.is_active:
            membership.is_active = True
            membership.role = invitation.role
            membership.save(update_fields=["is_active", "role", "updated_at"])

        invitation.accepted_at = timezone.now()
        invitation.save(update_fields=["accepted_at", "updated_at"])

        record_audit(
            organization=organization,
            action=AuditAction.MEMBER_JOINED,
            actor=user,
            target=membership,
            metadata={"role": membership.role},
            request=request,
        )
    return membership


@transaction.atomic
def change_member_role(
    *,
    actor_membership: Membership,
    target_membership: Membership,
    new_role: str,
    request: Any = None,
) -> Membership:
    """Change a member's role, refusing privilege escalation."""
    if target_membership.organization_id != actor_membership.organization_id:
        raise OrganizationError("That member belongs to a different organization.")

    if target_membership.pk == actor_membership.pk:
        raise OrganizationError("You cannot change your own role.")

    # The actor must be allowed to act on the role being replaced and to grant
    # the new one, so an Admin can neither demote an Owner nor mint one.
    if not can_manage_member(actor_membership.role, target_membership.role):
        raise OrganizationError("You cannot modify a member at or above your own role.")
    if not can_assign_role(actor_membership.role, new_role):
        raise OrganizationError("You cannot grant a role at or above your own.")

    previous_role = target_membership.role
    if previous_role == Role.OWNER and new_role != Role.OWNER:
        _assert_another_owner_remains(target_membership)

    target_membership.role = new_role
    target_membership.save(update_fields=["role", "updated_at"])

    record_audit(
        organization=target_membership.organization,
        action=AuditAction.ROLE_CHANGED,
        actor=actor_membership.user,
        target=target_membership,
        metadata={"from": previous_role, "to": new_role},
        request=request,
    )
    return target_membership


@transaction.atomic
def remove_member(
    *, actor_membership: Membership, target_membership: Membership, request: Any = None
) -> None:
    """Deactivate a membership, keeping the row for audit continuity."""
    if target_membership.organization_id != actor_membership.organization_id:
        raise OrganizationError("That member belongs to a different organization.")
    if target_membership.pk == actor_membership.pk:
        raise OrganizationError("You cannot remove yourself.")
    if not can_manage_member(actor_membership.role, target_membership.role):
        raise OrganizationError("You cannot remove a member at or above your own role.")

    if target_membership.role == Role.OWNER:
        _assert_another_owner_remains(target_membership)

    target_membership.is_active = False
    target_membership.save(update_fields=["is_active", "updated_at"])

    record_audit(
        organization=target_membership.organization,
        action=AuditAction.MEMBER_REMOVED,
        actor=actor_membership.user,
        target=target_membership,
        metadata={"role": target_membership.role},
        request=request,
    )
