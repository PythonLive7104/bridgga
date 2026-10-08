"""The ICP builder (PRD section 27).

Reads a confirmed company profile and drafts who that business should sell to.
Unlike the company-understanding agent this fetches nothing: its whole input is
a record the customer has already reviewed and agreed to, which is the point of
making them confirm it first. A bad ICP built on a bad profile is two layers of
wrong, and only one of them is visible.
"""

from __future__ import annotations

from typing import Any

import structlog
from django.db import transaction

from apps.ai.runner import run_prompt
from apps.ai.schemas import ICPDraft
from apps.common import ai_editing as editing
from apps.common.tenancy import tenant_context
from apps.intelligence.models import ICP, CompanyProfile, ICPStatus, ProfileStatus

logger = structlog.get_logger(__name__)


def describe_profile(profile: CompanyProfile) -> str:
    """Render a company profile as the agent's input.

    Only the fields that bear on *who would buy this*. Sending the whole record
    would spend tokens on evidence and provenance the agent cannot act on, and
    would bury the parts that matter.
    """
    lines: list[str] = []

    def add(label: str, value: Any) -> None:
        if isinstance(value, list):
            value = ", ".join(str(item) for item in value)
        if value:
            lines.append(f"{label}: {value}")

    add("Company", profile.company_name)
    add("Summary", profile.one_line_summary)
    add("Industry", profile.industry)
    add("Business model", profile.business_model)
    add("Products", profile.products)
    add("Value proposition", profile.value_proposition)
    add("Target customers", profile.target_customers)
    add("Use cases", profile.use_cases)
    add("Problems solved", profile.pain_points_solved)
    add("Pricing", profile.pricing_summary)
    add("Operates in", profile.geographies)
    add("Likely buyers", profile.buyer_personas)
    add("Named competitors", profile.competitors)

    # Carried through deliberately: a gap the profile admits to is a gap the
    # ICP should not paper over with a confident guess.
    add("The website did not say", profile.unknowns)

    return "\n".join(lines)


def generate_icp(
    *,
    organization: Any,
    icp: ICP | None = None,
    requested_by: Any = None,
    provider: Any = None,
) -> ICP:
    """Draft an ICP from the organization's company profile.

    Failures are recorded on the record rather than raised, for the same reason
    as the company agent: the customer needs to be told what went wrong.
    """
    with tenant_context(organization=organization):
        profile = CompanyProfile.objects.filter(organization=organization).first()
        if icp is None:
            icp = ICP.objects.create(organization=organization)

    if profile is None or profile.status == ProfileStatus.DRAFT:
        return _fail(icp, "Analyse your company website before generating an ICP.")

    source = describe_profile(profile)
    if not source.strip():
        return _fail(icp, "The company profile is empty. Fill it in or re-run the analysis.")

    with tenant_context(organization=organization):
        icp.status = ICPStatus.GENERATING
        icp.generation_error = ""
        icp.source_profile = profile
        icp.save(update_fields=["status", "generation_error", "source_profile", "updated_at"])

    try:
        result = run_prompt(
            organization=organization,
            prompt="icp_draft",
            user_content=source,
            feature="icp_builder",
            subject=icp,
            requested_by=requested_by,
            provider=provider,
            # The input is the customer's own reviewed profile, not a crawled
            # page. It is still fenced, because parts of it came from a website
            # originally and an edit does not launder that.
            untrusted=True,
        )
    except Exception as exc:
        logger.warning(
            "icp_generation_failed",
            organization_id=str(organization.public_id),
            error=str(exc)[:200],
        )
        return _fail(icp, f"The ICP could not be generated: {exc}")

    return apply_ai_output(icp=icp, output=result.output, prompt_pin=result.job.prompt_pin)


def apply_ai_output(*, icp: ICP, output: ICPDraft, prompt_pin: str = "") -> ICP:
    """Write agent output into the ICP, preserving human edits.

    The buyer profile arrives nested and is flattened here, because each part
    is separately editable and separately revertible: someone correcting the
    job titles should not have to re-accept the agent's guess at seniority.
    """
    values = output.model_dump(mode="json")
    buyer = values.pop("buyer", None) or {}
    values.update(
        {
            "job_titles": buyer.get("job_titles") or [],
            "departments": buyer.get("departments") or [],
            "seniority": buyer.get("seniority") or [],
            "responsibilities": buyer.get("responsibilities") or [],
        }
    )

    editing.apply_ai_output(
        record=icp,
        values=values,
        extra={
            "evidence": values.get("evidence") or [],
            "confidence": values.get("confidence") or "",
            "prompt_pin": prompt_pin,
            "generation_error": "",
            # Re-generating an active ICP leaves it active: campaigns and saved
            # searches point at it, and silently deactivating it would stop
            # them without telling anybody.
            "status": ICPStatus.ACTIVE if icp.is_active else ICPStatus.READY,
        },
    )

    logger.info(
        "icp_updated",
        organization_id=str(icp.organization.public_id),
        prompt=prompt_pin,
        preserved_edits=len(icp.edited_fields),
    )
    return icp


def apply_edits(*, icp: ICP, data: dict[str, Any]) -> list[str]:
    return editing.apply_edits(record=icp, data=data)


def reset_fields(*, icp: ICP, fields: list[str]) -> list[str]:
    return editing.reset_fields(record=icp, fields=fields)


@transaction.atomic
def activate(*, icp: ICP) -> ICP:
    """Make this the ICP that discovery and campaigns use by default.

    Deactivating the previous one first is not a convenience: the database
    holds a partial unique index allowing only one active ICP per
    organization, so setting this one without clearing the other fails.
    """
    with tenant_context(organization=icp.organization):
        ICP.objects.filter(organization=icp.organization, is_active=True).exclude(pk=icp.pk).update(
            is_active=False, status=ICPStatus.READY
        )

        icp.is_active = True
        icp.status = ICPStatus.ACTIVE
        icp.save(update_fields=["is_active", "status", "updated_at"])
    return icp


def _fail(icp: ICP, reason: str) -> ICP:
    with tenant_context(organization=icp.organization):
        icp.status = ICPStatus.FAILED
        icp.generation_error = reason[:255]
        icp.save(update_fields=["status", "generation_error", "updated_at"])
    return icp


__all__ = [
    "activate",
    "apply_ai_output",
    "apply_edits",
    "describe_profile",
    "generate_icp",
    "reset_fields",
]
