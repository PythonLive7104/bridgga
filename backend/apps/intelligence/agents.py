"""Company understanding (PRD section 26).

Reads a customer's website and produces an editable ``CompanyProfile``. This is
the first agent in the product and everything downstream depends on it: the
ICP, the market recommendation, the targeting and every generated message are
built on what this concludes. A wrong profile is not a cosmetic problem, which
is why the whole thing is editable and why a correction outranks a re-run.

Two decisions worth stating:

* **Several pages, not just the homepage.** PRD section 26 lists pricing,
  product, documentation and blog pages as inputs. A homepage states
  positioning; the pricing page states the business model. Crawling a handful
  of ranked internal links costs four cheap fetches and changes the quality of
  the answer.
* **The agent never overwrites a human.** ``apply_ai_output`` writes only into
  fields nobody has edited. See ``CompanyProfile`` for why.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

import structlog
from django.db import transaction
from django.utils import timezone

from apps.ai.runner import run_prompt
from apps.ai.schemas import CompanyProfile as CompanyProfileSchema
from apps.common import ai_editing as editing
from apps.common.tenancy import tenant_context
from apps.intelligence.extract import INTERESTING_PATH_HINTS
from apps.intelligence.models import (
    CompanyProfile,
    ProfileStatus,
    SnapshotStatus,
    WebsiteSnapshot,
)
from apps.intelligence.services import capture_snapshot, normalise_website_url

logger = structlog.get_logger(__name__)

#: Supporting pages fetched beyond the homepage. Four is a judgement, not a
#: constant to tune: each page costs a fetch and roughly a thousand prompt
#: tokens, and past the first few the marginal page is usually another blog
#: post rather than another fact about the business.
MAX_SUPPORTING_PAGES = 4

#: Characters of each supporting page included in the prompt. The homepage gets
#: the full budget; the rest are there for specifics such as a price or a named
#: integration, which appear early on the page.
SUPPORTING_PAGE_CHARS = 6_000


def _hint_for(url: str) -> str:
    """Which category of page a URL looks like, or "" for none."""
    path = urlsplit(url).path.lower()
    for hint in INTERESTING_PATH_HINTS:
        if hint in path:
            return hint
    return ""


def select_key_pages(snapshot: WebsiteSnapshot, *, limit: int = MAX_SUPPORTING_PAGES) -> list[str]:
    """Choose the supporting pages worth spending a crawl on.

    ``internal_links`` arrives already ranked by the extractor, so the naive
    choice is the first ``limit`` entries. That is wrong on a real site: a nav
    with /about, /about/team, /about/story and /about/careers would consume the
    whole budget on one category and never reach /pricing.

    So this takes the best page from each category before taking a second from
    any -- breadth first, because the categories are the point. The ranking
    within a category is left alone.
    """
    chosen: list[str] = []
    seen_hints: set[str] = set()
    deferred: list[str] = []

    for url in snapshot.internal_links:
        if url == snapshot.final_url or url == snapshot.requested_url:
            continue
        hint = _hint_for(url)
        if hint and hint not in seen_hints:
            seen_hints.add(hint)
            chosen.append(url)
            if len(chosen) == limit:
                return chosen
        else:
            deferred.append(url)

    # Budget left over: fall back to the ranked order for the remainder.
    for url in deferred:
        if len(chosen) == limit:
            break
        chosen.append(url)

    return chosen


def build_source_text(snapshots: list[WebsiteSnapshot]) -> str:
    """Flatten several pages into one body of evidence.

    Each page keeps its own ``URL:`` header so the model can attribute an
    evidence entry to the page it read it on, which is what makes the stored
    evidence checkable later (PRD section 58).
    """
    parts: list[str] = []
    for index, snapshot in enumerate(snapshots):
        if not snapshot.succeeded:
            continue
        budget = 12_000 if index == 0 else SUPPORTING_PAGE_CHARS
        parts.append(snapshot.summary_for_prompt(max_chars=budget))
    return "\n\n---\n\n".join(parts)


def get_or_create_profile(*, organization: Any) -> CompanyProfile:
    with tenant_context(organization=organization):
        profile, _ = CompanyProfile.objects.get_or_create(organization=organization)
        return profile


def analyze_company(
    *,
    organization: Any,
    url: str = "",
    requested_by: Any = None,
    max_pages: int = MAX_SUPPORTING_PAGES,
    provider: Any = None,
) -> CompanyProfile:
    """Crawl a website and write what the agent makes of it into the profile.

    Failures are recorded on the profile rather than raised. Onboarding needs
    to tell the customer *why* their site could not be read -- a refused fetch
    and an unreachable host call for different advice -- and an exception
    escaping into a Celery traceback tells them nothing.
    """
    profile = get_or_create_profile(organization=organization)
    target = normalise_website_url(url or profile.website or organization.website or "")

    if not target:
        return _fail(profile, "No website to analyse. Add one and try again.")

    with tenant_context(organization=organization):
        profile.website = target[:2048]
        profile.status = ProfileStatus.ANALYZING
        profile.analysis_error = ""
        profile.save(update_fields=["website", "status", "analysis_error", "updated_at"])

    home = capture_snapshot(organization=organization, url=target)
    if not home.succeeded:
        return _fail(
            profile,
            home.error_reason or "The website could not be read.",
            snapshots=[home],
        )

    snapshots = [home]
    for link in select_key_pages(home, limit=max_pages):
        page = capture_snapshot(organization=organization, url=link)
        if page.succeeded:
            snapshots.append(page)

    source_text = build_source_text(snapshots)
    if not source_text.strip():
        return _fail(profile, "The website returned no readable text.", snapshots=snapshots)

    try:
        result = run_prompt(
            organization=organization,
            prompt="company_profile",
            # Page content is attacker-controlled by definition: anyone can put
            # an instruction on a website and ask this product to read it.
            user_content=source_text,
            feature="company_understanding",
            subject=profile,
            requested_by=requested_by,
            provider=provider,
        )
    except Exception as exc:
        logger.warning(
            "company_analysis_failed",
            organization_id=str(organization.public_id),
            error=str(exc)[:200],
        )
        return _fail(profile, f"The analysis could not be completed: {exc}", snapshots=snapshots)

    return apply_ai_output(
        profile=profile,
        output=result.output,
        snapshots=snapshots,
        prompt_pin=result.job.prompt_pin,
    )


def apply_ai_output(
    *,
    profile: CompanyProfile,
    output: CompanyProfileSchema,
    snapshots: list[WebsiteSnapshot] | None = None,
    prompt_pin: str = "",
) -> CompanyProfile:
    """Write agent output into the profile, preserving human edits.

    The preservation rule itself lives in ``apps.common.ai_editing``; what is
    local to this agent is the run's own account of itself -- evidence, the
    pages read, the prompt version -- and one judgement about status.
    """
    values = output.model_dump(mode="json")

    editing.apply_ai_output(
        record=profile,
        values=values,
        extra={
            "evidence": values.get("evidence") or [],
            "unknowns": values.get("unknowns") or [],
            "confidence": values.get("confidence") or "",
            "prompt_pin": prompt_pin,
            "last_analyzed_at": timezone.now(),
            "analysis_error": "",
            # A re-analysis of a confirmed profile does not un-confirm it: the
            # customer already agreed to this, and the fields they agreed to
            # are exactly the ones preserved above.
            "status": (
                ProfileStatus.CONFIRMED
                if profile.status == ProfileStatus.CONFIRMED
                else ProfileStatus.READY
            ),
        },
    )

    if snapshots:
        with tenant_context(organization=profile.organization):
            profile.source_snapshots.set([s for s in snapshots if s.succeeded])

    logger.info(
        "company_profile_updated",
        organization_id=str(profile.organization.public_id),
        prompt=prompt_pin,
        preserved_edits=len(profile.edited_fields),
        pages=len(snapshots or []),
    )
    return profile


def apply_edits(*, profile: CompanyProfile, data: dict[str, Any]) -> list[str]:
    """Apply human edits. See ``apps.common.ai_editing.apply_edits``."""
    return editing.apply_edits(record=profile, data=data)


def reset_fields(*, profile: CompanyProfile, fields: list[str]) -> list[str]:
    """Restore the agent's version of edited fields."""
    return editing.reset_fields(record=profile, fields=fields)


@transaction.atomic
def confirm_profile(*, profile: CompanyProfile) -> CompanyProfile:
    """Onboarding step 3: the customer agrees this describes their business."""
    with tenant_context(organization=profile.organization):
        profile.status = ProfileStatus.CONFIRMED
        profile.confirmed_at = timezone.now()
        profile.save(update_fields=["status", "confirmed_at", "updated_at"])
    return profile


def _fail(
    profile: CompanyProfile,
    reason: str,
    *,
    snapshots: list[WebsiteSnapshot] | None = None,
) -> CompanyProfile:
    with tenant_context(organization=profile.organization):
        profile.status = ProfileStatus.FAILED
        profile.analysis_error = reason[:255]
        profile.save(update_fields=["status", "analysis_error", "updated_at"])
        if snapshots:
            profile.source_snapshots.set([s for s in snapshots if s.status != SnapshotStatus.OK])
    return profile


__all__ = [
    "MAX_SUPPORTING_PAGES",
    "analyze_company",
    "apply_ai_output",
    "apply_edits",
    "build_source_text",
    "confirm_profile",
    "get_or_create_profile",
    "reset_fields",
    "select_key_pages",
]
