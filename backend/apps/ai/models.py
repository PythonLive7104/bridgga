"""AI job records (PRD sections 57 and 59).

One row per model call: what was asked, which prompt version and model answered,
what it cost, and whether it succeeded. This is the audit trail that makes an
AI feature debuggable after the fact.

Cost accounting deliberately lives in ``billing.UsageRecord`` rather than a
second ledger here. PRD section 80 names both an ``AIJob`` and an ``AIUsage``
entity, but two tables holding spend means two numbers that can disagree, and
the billing ledger already carries model, tokens and estimated cost. ``AIJob``
links to its usage row instead.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import TenantOwnedModel


class AIJobStatus(models.TextChoices):
    PENDING = "pending", _("Pending")
    SUCCEEDED = "succeeded", _("Succeeded")
    INVALID_OUTPUT = "invalid_output", _("Invalid output")
    REFUSED = "refused", _("Refused by model")
    FAILED = "failed", _("Failed")


class AIJob(TenantOwnedModel):
    feature = models.CharField(
        _("feature"),
        max_length=64,
        db_index=True,
        help_text=_("Which product capability ran this."),
    )
    # Pinned as "name@version" so a quality regression can be attributed to a
    # prompt change rather than guessed at.
    prompt_name = models.CharField(_("prompt"), max_length=100, blank=True)
    prompt_version = models.PositiveIntegerField(_("prompt version"), default=0)
    #: Version of the shared standing rules (apps.ai.prompts.GUARDRAILS) in
    #: force for this call. 0 means the call predates the field.
    guardrails_version = models.PositiveSmallIntegerField(_("guardrails version"), default=0)

    provider = models.CharField(_("provider"), max_length=40, blank=True)
    model_id = models.CharField(_("model"), max_length=100, blank=True)
    tier = models.CharField(_("tier"), max_length=20, blank=True)

    status = models.CharField(
        _("status"), max_length=20, choices=AIJobStatus.choices, default=AIJobStatus.PENDING
    )
    error_reason = models.CharField(_("error reason"), max_length=255, blank=True)
    attempts = models.PositiveSmallIntegerField(_("attempts"), default=0)

    input_tokens = models.IntegerField(_("input tokens"), default=0)
    output_tokens = models.IntegerField(_("output tokens"), default=0)
    cache_read_tokens = models.IntegerField(_("cache read tokens"), default=0)
    cache_write_tokens = models.IntegerField(_("cache write tokens"), default=0)
    #: Thinking tokens, reported by the vendor *inside* ``output_tokens`` and
    #: billed at the output rate. Stored separately rather than summed, so the
    #: ledger can answer "what did we pay to deliberate?" -- on a cheap
    #: classification it has been 85% of the output.
    reasoning_tokens = models.IntegerField(_("reasoning tokens"), default=0)
    cost_micro_usd = models.BigIntegerField(
        _("cost (micro USD)"),
        default=0,
        help_text=_("Millionths of a USD, so sub-cent calls are not rounded to zero."),
    )

    latency_ms = models.FloatField(_("latency ms"), null=True, blank=True)

    # The validated output, kept so a downstream bug can be diagnosed without
    # paying to run the model again.
    output = models.JSONField(_("output"), default=dict, blank=True)

    # What this job was about, as a loose reference -- jobs outlive the objects
    # they describe, and a real FK would either block deletion or cascade the
    # audit trail away.
    subject_type = models.CharField(_("subject type"), max_length=100, blank=True)
    subject_id = models.CharField(_("subject id"), max_length=64, blank=True)

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ai_jobs",
    )
    usage_record = models.ForeignKey(
        "billing.UsageRecord",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ai_jobs",
    )

    class Meta:
        verbose_name = _("AI job")
        verbose_name_plural = _("AI jobs")
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["organization", "-created_at"], name="aijob_org_created_idx"),
            models.Index(fields=["organization", "feature"], name="aijob_org_feature_idx"),
            models.Index(fields=["subject_type", "subject_id"], name="aijob_subject_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.feature} via {self.model_id} ({self.status})"

    @property
    def prompt_pin(self) -> str:
        """What produced this output, e.g. ``company_profile@2g2``.

        The guardrails version is part of it because the rendered prompt is
        the standing rules plus the prompt's own text, and the rules can
        change without any prompt's version moving.

        Rows written before the version was recorded carry 0 and render in the
        old form. They genuinely do not know which rules they ran under, and
        printing a number for them would be a guess dressed as a record.
        """
        if not self.prompt_name:
            return ""
        pin = f"{self.prompt_name}@{self.prompt_version}"
        return f"{pin}g{self.guardrails_version}" if self.guardrails_version else pin

    @property
    def cost_usd(self) -> float:
        """For display only. Never use a float for billing arithmetic."""
        return self.cost_micro_usd / 1_000_000
