"""Abstract model bases.

Primary keys are internal ``BigAutoField``s for join performance; every row
also carries an immutable ``public_id`` UUID, and that is the only identifier
the API ever exposes (PRD section 80). Sequential integers in URLs invite
enumeration, and UUID primary keys make every foreign-key index wider.
"""

from __future__ import annotations

import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.managers import AllObjectsManager, TenantManager


class UUIDModel(models.Model):
    public_id = models.UUIDField(
        _("public id"),
        default=uuid.uuid4,
        unique=True,
        editable=False,
        db_index=True,
    )

    class Meta:
        abstract = True


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(_("created at"), auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        abstract = True


class BaseModel(UUIDModel, TimestampedModel):
    """Non-tenant base: platform-wide tables such as plans or country profiles."""

    class Meta:
        abstract = True


class TenantOwnedModel(BaseModel):
    """Base for every row that belongs to one customer.

    Subclassing this is what enrols a model in automatic query scoping and in
    the generic isolation test. A tenant-owned model that does not subclass it
    is invisible to both, so new models must inherit from here rather than
    declaring their own ``organization`` field.
    """

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
        db_index=True,
        verbose_name=_("organization"),
    )

    objects = TenantManager()
    all_objects = AllObjectsManager()

    class Meta:
        abstract = True
        base_manager_name = "all_objects"

    def __str__(self) -> str:
        return f"{self._meta.verbose_name} {self.public_id}"


class WorkspaceOwnedModel(TenantOwnedModel):
    """Base for rows that live inside a single workspace.

    ``organization`` is kept denormalised alongside ``workspace`` so that every
    tenant query can filter on one indexed column without a join, and so the
    isolation test has a single field to assert on across all models.
    """

    workspace = models.ForeignKey(
        "organizations.Workspace",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
        db_index=True,
        verbose_name=_("workspace"),
    )

    class Meta:
        abstract = True
        base_manager_name = "all_objects"

    def save(self, *args: object, **kwargs: object) -> None:
        # Keep the denormalised column honest rather than trusting callers.
        if self.workspace_id and not self.organization_id:
            self.organization_id = self.workspace.organization_id
        super().save(*args, **kwargs)  # type: ignore[arg-type]
