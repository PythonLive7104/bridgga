"""The research agent (PRD sections 34 and 35).

Everything before this read a website and described a business. This reads
*everything the platform knows about one prospect* and writes the brief a
salesperson uses — and, in `reason_to_contact`, the sentence the build plan
calls the highest-leverage string in the product.

That changes what correctness means. A wrong company profile wastes the
customer's afternoon; a wrong reason-to-contact goes out under their name to
somebody they want to do business with. So:

**The observation is verified, the implication is not.** The reason-to-contact
splits into a claim of fact about the prospect and an argument about the
seller's product. The first is checked against the supplied material and the
whole reason is dropped if it cannot be found there. The second is allowed to
be an inference, because inferring that your own product helps is the job.

**A missing reason is a correct answer.** Section 35 says every high-priority
prospect *should* have an explanation, and the temptation is to always produce
one. A reason the material cannot support is worse than none: it is a
fabrication the customer discovers in front of a buyer. When one is rejected,
``reason_rejected`` records why, because "nothing to say yet" and "the model
made something up" call for different responses.

**Personalization points are verified the same way,** each against its own
quote, for the same reason: they go into the message too.

**The context is assembled, not crawled.** Signals, their quoted evidence, the
company record, its technology and the latest page text are all already
stored. Re-fetching would be slower, costlier and no more current.
"""

from __future__ import annotations

import re
from typing import Any

import structlog
from django.db import transaction
from django.utils import timezone

from apps.ai.runner import run_prompt
from apps.ai.schemas import ProspectResearch as ResearchSchema
from apps.common import ai_editing as editing
from apps.common.tenancy import tenant_context
from apps.intelligence.research_models import ProspectResearch, ResearchStatus

logger = structlog.get_logger(__name__)

#: Characters of website text included. The signals and the company record
#: carry most of the value; page text is there for the specifics a model can
#: quote, and those sit near the top of a page.
MAX_PAGE_CHARS = 6_000

#: Live signals included, strongest first. Past a handful the marginal signal
#: is another "new pages" diff rather than another reason to call.
MAX_SIGNALS = 8

#: Shortest quote accepted as grounding. Anything shorter matches almost any
#: text and proves nothing. Same threshold as the signal interpreter.
MIN_QUOTE_CHARS = 12


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


def quote_is_grounded(quote: str, source: str) -> bool:
    """Whether a quote appears in the material the model was shown.

    Whitespace-insensitive, because a model reproducing a quote across a line
    break is quoting faithfully. Anything looser would defeat the purpose.
    """
    needle = _normalise(quote)
    return len(needle) >= MIN_QUOTE_CHARS and needle in _normalise(source)


# --------------------------------------------------------------------------- #
# Context
# --------------------------------------------------------------------------- #


def build_seller_context(*, organization: Any, icp: Any = None) -> str:
    """Who the customer is and who they are trying to reach.

    Passed as cacheable context rather than user content: it is identical for
    every prospect researched by one organization, so it is the part prompt
    caching can actually reuse (see ``CompletionRequest``).
    """
    from apps.intelligence.models import CompanyProfile

    with tenant_context(organization=organization):
        profile = CompanyProfile.objects.filter(organization=organization).first()

    parts: list[str] = ["SELLER (the customer of this platform)"]
    if profile:
        parts += [
            f"Company: {profile.company_name or organization.name}",
            f"What they sell: {profile.one_line_summary}" if profile.one_line_summary else "",
            f"Value proposition: {profile.value_proposition}" if profile.value_proposition else "",
            f"Products: {', '.join(profile.products)}" if profile.products else "",
            f"Target customers: {', '.join(profile.target_customers)}"
            if profile.target_customers
            else "",
            f"Problems they solve: {', '.join(profile.pain_points_solved)}"
            if profile.pain_points_solved
            else "",
        ]
    else:
        parts.append(f"Company: {organization.name}")

    if icp is not None:
        parts += [
            "",
            "IDEAL CUSTOMER PROFILE",
            f"Name: {icp.name}" if icp.name else "",
            f"Industries: {', '.join(icp.industries)}" if icp.industries else "",
            f"Countries: {', '.join(icp.countries)}" if icp.countries else "",
            f"Buyer titles: {', '.join(icp.job_titles)}" if icp.job_titles else "",
            "Watches for: "
            + ", ".join(
                f"{entry.get('type')} ({entry.get('description', '')})"
                for entry in (icp.pain_signals or [])
                if isinstance(entry, dict)
            )
            if icp.pain_signals
            else "",
        ]

    return "\n".join(part for part in parts if part)


def build_prospect_context(company: Any) -> tuple[str, list[Any], list[Any]]:
    """Everything known about the prospect, and what it was drawn from.

    Returns the text, the signals included and the snapshots included, so the
    record can store what was in view -- the answer to "is this brief based on
    the signal I am looking at?".
    """
    from apps.companies.models import CompanyTechnology, LeadSignal
    from apps.contacts.models import Person
    from apps.intelligence.models import SnapshotStatus, WebsiteSnapshot

    signals = list(
        LeadSignal.all_objects.filter(company_id=company.pk)
        .active()
        .strongest_first()[:MAX_SIGNALS]
    )
    technologies = list(
        CompanyTechnology.all_objects.filter(company_id=company.pk, is_current=True)[:20]
    )
    people = list(
        Person.all_objects.filter(company_id=company.pk).order_by("-is_decision_maker", "id")[:10]
    )
    snapshot = (
        WebsiteSnapshot.all_objects.filter(company_id=company.pk, status=SnapshotStatus.OK)
        .order_by("-fetched_at", "-id")
        .first()
    )

    parts: list[str] = [
        "PROSPECT",
        f"Name: {company.name}",
        f"Website: {company.website}" if company.website else "",
        f"Industry: {company.industry}" if company.industry else "",
        f"Location: {', '.join(filter(None, [company.city, company.country]))}"
        if (company.city or company.country)
        else "",
        f"Size: {company.employee_range}" if company.employee_range else "",
        f"Business model: {company.business_model}" if company.business_model else "",
        f"Founded: {company.founded_year}" if company.founded_year else "",
        f"Description: {company.description}" if company.description else "",
    ]

    if technologies:
        parts += ["", "TECHNOLOGY IN USE: " + ", ".join(t.name for t in technologies)]

    if signals:
        parts += ["", "BUYING SIGNALS DETECTED"]
        for signal in signals:
            observed = (signal.occurred_at or signal.detected_at).date().isoformat()
            parts.append(
                f"- [{signal.signal_type}] {signal.title} "
                f"(observed {observed}, strength {signal.decayed_strength()}/100)"
            )
            # The quotes are what the model is allowed to quote back. Without
            # them in the context, a verified reason-to-contact is impossible:
            # there would be nothing to verify it against.
            for entry in (signal.evidence or [])[:2]:
                quote = (entry.get("quote") or "").strip()
                if quote:
                    parts.append(f'    evidence: "{quote}" ({entry.get("source_url", "")})')

    if people:
        parts += ["", "KNOWN CONTACTS (roles only)"]
        parts += [
            f"- {person.job_title or 'unknown role'}"
            + (" (decision maker)" if person.is_decision_maker else "")
            for person in people
        ]

    if snapshot:
        parts += ["", "WEBSITE TEXT", snapshot.summary_for_prompt(max_chars=MAX_PAGE_CHARS)]

    return (
        "\n".join(part for part in parts if part),
        signals,
        [snapshot] if snapshot else [],
    )


# --------------------------------------------------------------------------- #
# Verification
# --------------------------------------------------------------------------- #


def verified_reason(reason: Any, source: str) -> tuple[dict[str, Any] | None, str]:
    """Check a reason-to-contact against the material. Returns (reason, why not).

    This is what makes section 35's "must be evidence-based" a property of the
    system rather than a request in a prompt. The observation is a claim of
    fact; if no evidence quote for it appears in the material, the reason is
    rejected whole -- storing the implication alone would leave a sales
    argument with nothing behind it.
    """
    if reason is None:
        return None, "The agent did not produce one."

    if not reason.observation.strip():
        return None, "No observation was stated."

    grounded = [
        entry
        for entry in (reason.evidence or [])
        if entry.quote and quote_is_grounded(entry.quote, source)
    ]
    if not grounded:
        return None, "The evidence for the observation could not be found in the source material."

    return {
        "observation": reason.observation,
        "implication": reason.implication,
        "evidence": [entry.model_dump(mode="json") for entry in grounded],
        "confidence": str(reason.confidence),
    }, ""


def verified_points(points: list[Any], source: str) -> list[dict[str, Any]]:
    """Keep only the personalization points whose quote is in the material."""
    return [
        point.model_dump(mode="json")
        for point in points
        if quote_is_grounded(point.source_quote, source)
    ]


def verified_evidence(entries: list[Any], source: str) -> list[dict[str, Any]]:
    """Drop evidence entries quoting something that is not there.

    An entry with no quote is kept: a claim attributed to a page without a
    verbatim excerpt is weaker, not false, and the URL is still checkable.
    """
    kept: list[dict[str, Any]] = []
    for entry in entries or []:
        quote = (entry.quote or "").strip()
        if quote and not quote_is_grounded(quote, source):
            continue
        kept.append(entry.model_dump(mode="json"))
    return kept


# --------------------------------------------------------------------------- #
# The agent
# --------------------------------------------------------------------------- #


def get_or_create_research(*, company: Any, icp: Any = None) -> ProspectResearch:
    with tenant_context(organization=company.organization):
        research, _ = ProspectResearch.objects.get_or_create(
            company=company,
            icp=icp,
            defaults={"organization": company.organization},
        )
        return research


def research_company(
    *,
    company: Any,
    icp: Any = None,
    provider: Any = None,
    requested_by: Any = None,
) -> ProspectResearch:
    """Research one prospect and store the brief.

    Failures are recorded on the record rather than raised: this runs in a
    worker, and a traceback in a log tells the person waiting for the brief
    nothing about why it is not there.
    """
    from apps.intelligence.models import ICP

    organization = company.organization

    if icp is None:
        with tenant_context(organization=organization):
            icp = ICP.objects.filter(organization=organization, is_active=True).first()

    research = get_or_create_research(company=company, icp=icp)

    with tenant_context(organization=organization):
        research.status = ResearchStatus.RESEARCHING
        research.research_error = ""
        research.save(update_fields=["status", "research_error", "updated_at"])

    prospect_text, signals, snapshots = build_prospect_context(company)
    seller_text = build_seller_context(organization=organization, icp=icp)

    if len(_normalise(prospect_text)) < 120:
        return _fail(research, "There is too little known about this company to research it.")

    try:
        result = run_prompt(
            organization=organization,
            prompt="prospect_research",
            # The prospect's own material is attacker-controlled: its website
            # text and the quotes from its pages are in here.
            user_content=prospect_text,
            cacheable_context=seller_text,
            feature="prospect_research",
            subject=company,
            requested_by=requested_by,
            provider=provider,
        )
    except Exception as exc:
        logger.warning(
            "prospect_research_failed",
            company_id=str(company.public_id),
            error=str(exc)[:200],
        )
        return _fail(research, f"The research could not be completed: {exc}")

    return apply_research(
        research=research,
        output=result.output,
        source=f"{seller_text}\n{prospect_text}",
        prompt_pin=result.job.prompt_pin,
        signals=signals,
        snapshots=snapshots,
    )


@transaction.atomic
def apply_research(
    *,
    research: ProspectResearch,
    output: ResearchSchema,
    source: str,
    prompt_pin: str = "",
    signals: list[Any] | None = None,
    snapshots: list[Any] | None = None,
) -> ProspectResearch:
    """Write verified output into the record, preserving human edits."""
    reason, rejected = verified_reason(output.reason_to_contact, source)
    points = verified_points(output.personalization_points, source)

    dropped_points = len(output.personalization_points) - len(points)
    if rejected and output.reason_to_contact is not None:
        logger.info(
            "reason_to_contact_rejected",
            company_id=str(research.company_id),
            reason=rejected,
        )

    values = {
        "summary": output.summary,
        "why_they_may_buy": output.why_they_may_buy,
        "likely_pain": output.likely_pain,
        "possible_use_case": output.possible_use_case,
        "suggested_approach": output.suggested_approach,
        "personalization_points": points,
        "decision_maker_titles": output.decision_maker_titles,
        "reason_observation": (reason or {}).get("observation", ""),
        "reason_implication": (reason or {}).get("implication", ""),
    }

    editing.apply_ai_output(
        record=research,
        values=values,
        extra={
            "reason_evidence": (reason or {}).get("evidence", []),
            "reason_confidence": (reason or {}).get("confidence", ""),
            "reason_rejected": "" if reason else rejected,
            "evidence": verified_evidence(output.evidence, source),
            "unknowns": output.unknowns,
            "confidence": str(output.confidence),
            "prompt_pin": prompt_pin,
            "researched_at": timezone.now(),
            "research_error": "",
            "status": ResearchStatus.READY,
            "score_at_research": _current_score(research),
        },
    )

    with tenant_context(organization=research.organization):
        if signals is not None:
            research.source_signals.set(signals)
        if snapshots is not None:
            research.source_snapshots.set([s for s in snapshots if s])

    logger.info(
        "prospect_researched",
        company_id=str(research.company_id),
        prompt=prompt_pin,
        has_reason=research.has_reason,
        dropped_points=dropped_points,
        signals=len(signals or []),
    )
    return research


def apply_edits(*, research: ProspectResearch, data: dict[str, Any]) -> list[str]:
    """Apply a human's corrections. See ``apps.common.ai_editing.apply_edits``.

    An edited reason keeps the evidence the agent verified. That is deliberate:
    a rep rewording an observation is rewording the same fact, and stripping
    the evidence would turn a checkable claim into a free-text flourish, which
    is the thing section 35 forbids.
    """
    return editing.apply_edits(record=research, data=data)


def reset_fields(*, research: ProspectResearch, fields: list[str]) -> list[str]:
    return editing.reset_fields(record=research, fields=fields)


def _current_score(research: ProspectResearch) -> int | None:
    from apps.leads.models import Lead

    lead = (
        Lead.all_objects.filter(company_id=research.company_id, icp_id=research.icp_id)
        .order_by("-score")
        .first()
    )
    return lead.score if lead else None


def _fail(research: ProspectResearch, reason: str) -> ProspectResearch:
    with tenant_context(organization=research.organization):
        research.status = ResearchStatus.FAILED
        research.research_error = reason[:255]
        research.save(update_fields=["status", "research_error", "updated_at"])
    return research


__all__ = [
    "MAX_SIGNALS",
    "MIN_QUOTE_CHARS",
    "apply_edits",
    "apply_research",
    "build_prospect_context",
    "build_seller_context",
    "get_or_create_research",
    "quote_is_grounded",
    "research_company",
    "reset_fields",
    "verified_evidence",
    "verified_points",
    "verified_reason",
]
