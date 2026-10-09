"""Saved prospect searches (PRD section 29).

A saved search stores the *filters*, never the results. Running it again is
the point: a search for "logistics companies in Lagos that started hiring"
should surface the companies that match today, not the ones that matched when
it was saved. Storing results would turn a live question into a stale list.
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import TenantOwnedModel


class SavedSearch(TenantOwnedModel):
    name = models.CharField(_("name"), max_length=150)
    description = models.CharField(_("description"), max_length=300, blank=True)

    #: The ProspectFilters payload, as submitted. Stored as given rather than
    #: normalised, so a filter added later does not silently change what an
    #: existing saved search means.
    filters = models.JSONField(_("filters"), default=dict)

    #: Shared searches are how a team works one definition of a good prospect
    #: rather than five private approximations of it.
    is_shared = models.BooleanField(_("shared with the workspace"), default=False)

    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="saved_searches",
        verbose_name=_("created by"),
    )
    last_run_at = models.DateTimeField(_("last run"), null=True, blank=True)
    last_result_count = models.PositiveIntegerField(_("last result count"), default=0)

    class Meta:
        verbose_name = _("saved search")
        verbose_name_plural = _("saved searches")
        ordering = ["name", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name"], name="one_saved_search_name_per_org"
            )
        ]

    def __str__(self) -> str:
        return self.name
