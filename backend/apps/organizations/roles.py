"""Roles and the capability matrix (PRD section 66).

Authorisation is expressed as capabilities rather than role checks scattered
through views. A view declares the capability it needs; this table decides who
has it. Adding a role means adding one row, not auditing every endpoint.

The capability list intentionally covers later phases so that permissions do
not need re-modelling when campaigns, conversations and integrations land.
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _


class Role(models.TextChoices):
    OWNER = "owner", _("Owner")
    ADMIN = "admin", _("Admin")
    MANAGER = "manager", _("Manager")
    SALES_REP = "sales_rep", _("Sales rep")
    VIEWER = "viewer", _("Viewer")


# Lower rank means more authority. Used to stop privilege escalation: nobody
# may grant or revoke a role at or above their own.
ROLE_RANK: dict[str, int] = {
    Role.OWNER: 0,
    Role.ADMIN: 1,
    Role.MANAGER: 2,
    Role.SALES_REP: 3,
    Role.VIEWER: 4,
}


class Capability(models.TextChoices):
    ORG_VIEW = "org.view", _("View organization")
    ORG_MANAGE = "org.manage", _("Manage organization")
    ORG_DELETE = "org.delete", _("Delete organization")

    MEMBER_VIEW = "member.view", _("View members")
    MEMBER_INVITE = "member.invite", _("Invite members")
    MEMBER_MANAGE = "member.manage", _("Manage members and roles")

    WORKSPACE_VIEW = "workspace.view", _("View workspaces")
    WORKSPACE_MANAGE = "workspace.manage", _("Manage workspaces")

    BILLING_VIEW = "billing.view", _("View billing")
    BILLING_MANAGE = "billing.manage", _("Manage billing")

    APIKEY_MANAGE = "apikey.manage", _("Manage API keys")
    AUDIT_VIEW = "audit.view", _("View audit log")
    EXPORT_CREATE = "export.create", _("Export data")

    ICP_MANAGE = "icp.manage", _("Manage ICPs")
    PROSPECT_VIEW = "prospect.view", _("View prospects")
    PROSPECT_MANAGE = "prospect.manage", _("Manage prospects")

    CAMPAIGN_VIEW = "campaign.view", _("View campaigns")
    CAMPAIGN_MANAGE = "campaign.manage", _("Manage campaigns")
    CAMPAIGN_LAUNCH = "campaign.launch", _("Launch campaigns")

    CONVERSATION_VIEW = "conversation.view", _("View conversations")
    CONVERSATION_REPLY = "conversation.reply", _("Reply to conversations")

    PIPELINE_VIEW = "pipeline.view", _("View pipeline")
    PIPELINE_MANAGE = "pipeline.manage", _("Manage pipeline")

    ANALYTICS_VIEW = "analytics.view", _("View analytics")
    INTEGRATION_MANAGE = "integration.manage", _("Manage integrations")
    COMPLIANCE_MANAGE = "compliance.manage", _("Manage compliance settings")


_ALL: frozenset[str] = frozenset(Capability.values)

_VIEW_ONLY: frozenset[str] = frozenset(
    {
        Capability.ORG_VIEW,
        Capability.MEMBER_VIEW,
        Capability.WORKSPACE_VIEW,
        Capability.PROSPECT_VIEW,
        Capability.CAMPAIGN_VIEW,
        Capability.CONVERSATION_VIEW,
        Capability.PIPELINE_VIEW,
        Capability.ANALYTICS_VIEW,
    }
)

_SALES_REP: frozenset[str] = _VIEW_ONLY | {
    Capability.PROSPECT_MANAGE,
    Capability.CONVERSATION_REPLY,
    Capability.PIPELINE_MANAGE,
}

_MANAGER: frozenset[str] = _SALES_REP | {
    Capability.ICP_MANAGE,
    Capability.CAMPAIGN_MANAGE,
    Capability.CAMPAIGN_LAUNCH,
    Capability.EXPORT_CREATE,
    Capability.BILLING_VIEW,
}

# Admin runs the workspace and the team but does not own the money: changing
# the subscription or deleting the organization stays with the Owner.
_ADMIN: frozenset[str] = _MANAGER | {
    Capability.ORG_MANAGE,
    Capability.MEMBER_INVITE,
    Capability.MEMBER_MANAGE,
    Capability.WORKSPACE_MANAGE,
    Capability.APIKEY_MANAGE,
    Capability.AUDIT_VIEW,
    Capability.INTEGRATION_MANAGE,
    Capability.COMPLIANCE_MANAGE,
}

ROLE_CAPABILITIES: dict[str, frozenset[str]] = {
    Role.OWNER: _ALL,
    Role.ADMIN: _ADMIN,
    Role.MANAGER: _MANAGER,
    Role.SALES_REP: _SALES_REP,
    Role.VIEWER: _VIEW_ONLY,
}


def capabilities_for(role: str) -> frozenset[str]:
    return ROLE_CAPABILITIES.get(role, frozenset())


def role_has_capability(role: str, capability: str) -> bool:
    return capability in capabilities_for(role)


def can_assign_role(actor_role: str, target_role: str) -> bool:
    """Whether ``actor_role`` may grant ``target_role``.

    Everyone below Owner may grant only strictly lower ranks, so an Admin
    cannot mint an Owner and cannot sidegrade another Admin (PRD section 108:
    privilege escalation).

    Owner is the exception, because ownership has to be transferable: an Owner
    who could not grant Owner would make succession impossible without staff
    intervention. The "at least one owner" invariant in the service layer is
    what keeps that from stranding an organization.
    """
    if actor_role not in ROLE_RANK or target_role not in ROLE_RANK:
        return False
    if actor_role == Role.OWNER:
        return True
    return ROLE_RANK[actor_role] < ROLE_RANK[target_role]


def can_manage_member(actor_role: str, target_role: str) -> bool:
    """Whether ``actor_role`` may modify or remove a member holding ``target_role``.

    Same shape as :func:`can_assign_role`: strictly senior, except that an
    Owner may act on a co-owner. Without that, two owners would permanently
    deadlock each other.
    """
    if actor_role not in ROLE_RANK or target_role not in ROLE_RANK:
        return False
    if actor_role == Role.OWNER:
        return True
    return ROLE_RANK[actor_role] < ROLE_RANK[target_role]


__all__ = [
    "ROLE_CAPABILITIES",
    "ROLE_RANK",
    "Capability",
    "Role",
    "can_assign_role",
    "can_manage_member",
    "capabilities_for",
    "role_has_capability",
]
