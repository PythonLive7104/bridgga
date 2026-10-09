"""Abstract model bases.

Primary keys are internal ``BigAutoField``s for join performance; every row
also carries an immutable ``public_id`` UUID, and that is the only identifier
the API ever exposes (PRD section 80). Sequential integers in URLs invite
enumeration, and UUID primary keys make every foreign-key index wider.
"""

from __future__ import annotations

import uuid
from typing import Any

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


class AIEditableModel(TenantOwnedModel):
    """Base for a record an agent writes and a human corrects.

    Any such record has the same problem, first met in ``CompanyProfile``: the
    agent re-runs, and the obvious implementation discards every correction the
    customer made. Solving it once per model means solving it differently per
    model, and getting it subtly wrong in at least one of them.

    So the rule lives here. ``ai_values`` holds what the agent last produced
    and ``edited_fields`` records what a human changed since. A re-run writes
    only into untouched fields, a correction survives until explicitly reset,
    and because the agent's version is still stored the edit stays reversible.

    Subclasses declare ``AI_FIELDS``. Everything generic -- applying output,
    detecting edits, reverting them, serialising provenance -- iterates that
    tuple, so adding a field means adding it there and nowhere else.
    """

    #: Fields the agent populates, and therefore the editable surface.
    AI_FIELDS: tuple[str, ...] = ()

    ai_values = models.JSONField(_("AI values"), default=dict, blank=True)
    edited_fields = models.JSONField(_("human-edited fields"), default=list, blank=True)

    class Meta:
        abstract = True
        base_manager_name = "all_objects"

    def was_edited(self, field: str) -> bool:
        return field in self.edited_fields

    def ai_value_for(self, field: str) -> Any:
        """What the agent last produced for a field, regardless of later edits."""
        return self.ai_values.get(field)

    def empty_value_for(self, field: str) -> Any:
        """The empty value matching a field's type.

        A cleared list field has to come back as ``[]`` rather than ``""``, or
        the API starts returning a string where its schema promises an array.
        """
        return [] if isinstance(self._meta.get_field(field), models.JSONField) else ""

    def fields_meta(self) -> dict[str, dict[str, Any]]:
        """Per-field provenance for the API: edited, and what the AI said."""
        return {
            field: {"edited": self.was_edited(field), "ai_value": self.ai_value_for(field)}
            for field in self.AI_FIELDS
        }


class ContactStatus(models.TextChoices):
    """The six statuses PRD section 60 names, and only those.

    The order matters for display, not for comparison: there is no sense in
    which `risky` is "between" `verified` and `invalid`, and anything that
    needs to rank them should say so explicitly rather than rely on this.
    """

    UNKNOWN = "unknown", _("Unknown")
    VERIFIED = "verified", _("Verified")
    RISKY = "risky", _("Risky")
    INVALID = "invalid", _("Invalid")
    BOUNCED = "bounced", _("Bounced")
    UNSUBSCRIBED = "unsubscribed", _("Unsubscribed")


#: Statuses that must never be contacted again. `bounced` is included because
#: sending to a known-bad address is how a sending domain loses its reputation,
#: and `unsubscribed` because section 63 makes it a compliance matter rather
#: than a preference. The send path checks this, never the raw status string.
UNSENDABLE_CONTACT_STATUSES = frozenset(
    {
        ContactStatus.INVALID,
        ContactStatus.BOUNCED,
        ContactStatus.UNSUBSCRIBED,
    }
)


class Confidence(models.TextChoices):
    HIGH = "high", _("High")
    MEDIUM = "medium", _("Medium")
    LOW = "low", _("Low")


class ProvenancedModel(models.Model):
    """Where a record came from (PRD section 61).

    Every externally-sourced row carries this. The requirement is not
    bookkeeping: section 58 says the platform must still be able to produce the
    source and the retrieval time behind any claim, and section 61 adds that a
    data provider's usage rights have to be reviewable. A row whose origin is
    unknown cannot be defended to a customer, deleted on request with
    confidence, or dropped when a provider contract ends.

    ``usage_license`` is the field that makes the last of those possible. It
    records *under what terms* the data may be used, so a licence that lapses
    is a query rather than an investigation.
    """

    source = models.CharField(
        _("source"),
        max_length=100,
        blank=True,
        help_text=_("Where this came from, e.g. website_crawl, csv_import, provider:acme."),
    )
    source_url = models.URLField(_("source URL"), max_length=2048, blank=True)
    collected_at = models.DateTimeField(_("collected at"), null=True, blank=True, db_index=True)
    last_verified_at = models.DateTimeField(_("last verified at"), null=True, blank=True)
    confidence = models.CharField(
        _("confidence"),
        max_length=10,
        choices=Confidence.choices,
        default=Confidence.MEDIUM,
    )
    usage_license = models.CharField(
        _("usage licence"),
        max_length=100,
        blank=True,
        help_text=_("Terms this data may be used under, where a provider imposes any."),
    )

    class Meta:
        abstract = True

    @property
    def is_stale(self) -> bool:
        """True when nothing has re-confirmed this within the freshness window.

        Deliberately a property rather than a stored flag: staleness is a
        function of the clock, and a column would be wrong the moment it was
        written.
        """
        from django.conf import settings
        from django.utils import timezone

        checked = self.last_verified_at or self.collected_at
        if checked is None:
            return True
        days = getattr(settings, "DATA_FRESHNESS_DAYS", 90)
        return (timezone.now() - checked).days > days
