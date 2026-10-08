"""Audit log (PRD section 111).

Append-only by convention and by API: there is no update or delete endpoint,
and the admin registers it read-only. An audit trail a tenant can edit is not
an audit trail.

The actor is kept as both a nullable FK and a denormalised email string, so the
record still says who did what after the user row is deleted under a data
deletion request (PRD section 121).
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import TenantOwnedModel


class AuditAction(models.TextChoices):
    LOGIN = "login", _("Login")
    LOGIN_FAILED = "login_failed", _("Login failed")
    LOGOUT = "logout", _("Logout")
    MFA_ENABLED = "mfa_enabled", _("MFA enabled")
    MFA_DISABLED = "mfa_disabled", _("MFA disabled")

    ORGANIZATION_CREATED = "organization_created", _("Organization created")
    ORGANIZATION_UPDATED = "organization_updated", _("Organization updated")
    ORGANIZATION_DELETED = "organization_deleted", _("Organization deleted")

    WORKSPACE_CREATED = "workspace_created", _("Workspace created")
    WORKSPACE_DELETED = "workspace_deleted", _("Workspace deleted")

    MEMBER_INVITED = "member_invited", _("Member invited")
    MEMBER_JOINED = "member_joined", _("Member joined")
    MEMBER_REMOVED = "member_removed", _("Member removed")
    ROLE_CHANGED = "role_changed", _("Role changed")

    APIKEY_CREATED = "apikey_created", _("API key created")
    APIKEY_REVOKED = "apikey_revoked", _("API key revoked")
    INTEGRATION_CREATED = "integration_created", _("Integration created")

    CAMPAIGN_LAUNCHED = "campaign_launched", _("Campaign launched")
    CAMPAIGN_PAUSED = "campaign_paused", _("Campaign paused")
    AUTOPILOT_ENABLED = "autopilot_enabled", _("AI autopilot enabled")

    DATA_EXPORTED = "data_exported", _("Data exported")
    DATA_DELETED = "data_deleted", _("Data deleted")
    BILLING_CHANGED = "billing_changed", _("Billing changed")
    COMPLIANCE_CHANGED = "compliance_changed", _("Compliance settings changed")


class AuditLog(TenantOwnedModel):
    action = models.CharField(_("action"), max_length=64, choices=AuditAction.choices)

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_entries",
    )
    actor_email = models.EmailField(_("actor email"), blank=True)

    # Free-form target reference rather than a generic FK: audit rows outlive
    # the objects they describe, and a ContentType FK would either block
    # deletion or cascade the evidence away.
    target_type = models.CharField(_("target type"), max_length=100, blank=True)
    target_id = models.CharField(_("target id"), max_length=64, blank=True)
    target_label = models.CharField(_("target label"), max_length=255, blank=True)

    metadata = models.JSONField(_("metadata"), default=dict, blank=True)

    ip_address = models.GenericIPAddressField(_("IP address"), null=True, blank=True)
    user_agent = models.CharField(_("user agent"), max_length=400, blank=True)
    request_id = models.CharField(_("request id"), max_length=64, blank=True, db_index=True)

    class Meta:
        verbose_name = _("audit log entry")
        verbose_name_plural = _("audit log")
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["organization", "-created_at"], name="audit_org_created_idx"),
            models.Index(fields=["organization", "action"], name="audit_org_action_idx"),
            models.Index(fields=["target_type", "target_id"], name="audit_target_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.action} by {self.actor_email or 'system'}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.actor_id and not self.actor_email:
            self.actor_email = self.actor.email
        super().save(*args, **kwargs)
