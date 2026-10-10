"""Running a website sales audit (PRD sections 49 and 17).

Fetch the page, measure what can be measured, ask a model only about the three
things that cannot be, and combine them into one score that says which half it
came from.

Three decisions shape this module.

**The measured half runs first and stands alone.** If the model call fails,
the audit is still served with five dimensions of checkable findings. Section
17 promised a useful free result, and an error page for a visitor who pasted
their URL is the worst possible first impression of the product.

**An unscoreable dimension is dropped, not zeroed.** The same rule as the
opportunity score (ADR 0009): the weight of a dimension that could not be
assessed is redistributed across the ones that were, so a measured-only audit
reads out of what it actually measured rather than being capped at half.

**The same URL is not audited twice in an hour.** It is a public endpoint that
crawls a site and calls a paid model, which is to say it is a way to spend
somebody else's money and somebody else's bandwidth. A recent result is
returned instead.
"""

from __future__ import annotations

from typing import Any

import structlog
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.ai.runner import run_prompt
from apps.intelligence import audit_checks as checks_module
from apps.intelligence.audit_checks import (
    CONVERSION,
    DIMENSION_WEIGHTS,
    ICP_CLARITY,
    MEASURED_DIMENSIONS,
    VALUE_PROPOSITION,
)
from apps.intelligence.audit_models import AuditStatus, WebsiteAudit
from apps.intelligence.fetcher import FetchError, UnsafeUrlError, fetch_url
from apps.intelligence.services import normalise_website_url

logger = structlog.get_logger(__name__)

#: Minutes a result is reused for the same URL. Long enough to absorb a
#: visitor refreshing or sharing the link, short enough that somebody fixing
#: their page can see the difference the same morning.
DEFAULT_CACHE_MINUTES = 60


def cache_minutes() -> int:
    return int(getattr(settings, "WEBSITE_AUDIT_CACHE_MINUTES", DEFAULT_CACHE_MINUTES))


def recent_audit(url: str) -> WebsiteAudit | None:
    """A ready audit of this URL from within the cache window."""
    since = timezone.now() - timezone.timedelta(minutes=cache_minutes())
    return (
        WebsiteAudit.objects.filter(url=url, status=AuditStatus.READY, created_at__gte=since)
        .order_by("-created_at")
        .first()
    )


def public_tools_organization() -> Any:
    """The tenant that anonymous free-tool usage is billed to.

    An AI job belongs to an organization, and an anonymous visitor has none.
    Rather than skip the ledger -- which would make the free tool the one
    thing in the product whose cost nobody could see, when it is the thing
    most likely to be abused -- its spend lands here.

    It has no members, so it is reachable through no login and appears in
    nobody's workspace list.
    """
    from apps.organizations.models import Organization

    organization, _ = Organization.objects.get_or_create(
        slug="public-tools",
        defaults={
            "name": "Public tools",
            "default_currency": "USD",
            "timezone": "UTC",
        },
    )
    return organization


def judge(
    audit: WebsiteAudit,
    facts: Any,
    checks: list[Any],
    *,
    organization: Any,
    provider: Any = None,
    requested_by: Any = None,
) -> Any:
    """The model's half. Returns the output, or None if it could not run."""
    try:
        result = run_prompt(
            organization=organization,
            prompt="website_audit",
            # A page submitted by a stranger, read by a model: untrusted by
            # every definition the platform has.
            user_content=checks_module.describe_for_prompt(facts, checks),
            feature="website_audit",
            subject=audit,
            requested_by=requested_by,
            provider=provider,
        )
    except Exception as exc:
        # Logged, not raised. The measured half is already done and is worth
        # serving on its own.
        logger.warning("website_audit_judgement_failed", url=audit.url, error=str(exc)[:200])
        return None
    return result


@transaction.atomic
def _store(
    audit: WebsiteAudit,
    *,
    facts: Any,
    checks: list[Any],
    judgement: Any = None,
    prompt_pin: str = "",
) -> WebsiteAudit:
    scores = {
        dimension: checks_module.score_dimension(checks, dimension)
        for dimension in MEASURED_DIMENSIONS
    }
    notes: dict[str, str] = {}

    if judgement is not None:
        scores[VALUE_PROPOSITION] = judgement.value_proposition_score
        scores[ICP_CLARITY] = judgement.icp_clarity_score
        scores[CONVERSION] = judgement.conversion_score
        notes = {
            VALUE_PROPOSITION: judgement.value_proposition_note,
            ICP_CLARITY: judgement.icp_clarity_note,
            CONVERSION: judgement.conversion_note,
        }
        audit.what_they_sell = judgement.what_they_sell[:300]
        audit.who_its_for = judgement.who_its_for[:300]
        audit.confidence = str(judgement.confidence)
        audit.recommendations = [item.model_dump(mode="json") for item in judgement.recommendations]

    # Weight only over what was scored, so a measured-only audit is a score
    # out of what it measured rather than one capped at 60 (ADR 0009).
    weighted = sum(scores[dimension] * DIMENSION_WEIGHTS[dimension] for dimension in scores)
    total_weight = sum(DIMENSION_WEIGHTS[dimension] for dimension in scores)

    audit.scores = scores
    audit.notes = notes
    audit.overall_score = round(weighted / total_weight) if total_weight else 0
    audit.checks = [check.as_dict() for check in checks]
    audit.performance = checks_module.performance_observations(facts)
    audit.judged = judgement is not None
    audit.page_title = facts.title[:300]
    audit.page_description = facts.description
    audit.page_bytes = facts.bytes
    audit.elapsed_ms = facts.elapsed_ms
    audit.prompt_pin = prompt_pin
    audit.status = AuditStatus.READY
    audit.error_reason = ""
    audit.fetched_at = timezone.now()
    audit.save()
    return audit


def run_website_audit(
    *,
    url: str,
    organization: Any = None,
    requested_by: Any = None,
    email: str = "",
    provider: Any = None,
    use_cache: bool = True,
) -> WebsiteAudit:
    """Audit one page (PRD section 49).

    Never raises for a bad URL or an unreachable site: this is a public form,
    and the person who typed the address needs to be told what went wrong in
    words, not handed a 500.
    """
    target = normalise_website_url(url)[:2048]
    if not target:
        return _failed(url=url, reason="That does not look like a web address.")

    if use_cache:
        cached = recent_audit(target)
        if cached is not None:
            logger.info("website_audit_served_from_cache", url=target)
            return cached

    audit = WebsiteAudit.objects.create(
        url=target,
        organization=organization,
        requested_by=requested_by if getattr(requested_by, "pk", None) else None,
        email=email,
        status=AuditStatus.RUNNING,
    )

    try:
        result = fetch_url(target)
    except UnsafeUrlError as exc:
        return _fail(audit, exc.reason)
    except FetchError as exc:
        return _fail(audit, str(exc))

    from urllib.parse import urlsplit

    audit.final_url = result.final_url[:2048]
    audit.domain = (urlsplit(result.final_url).hostname or "").removeprefix("www.")[:255]
    audit.content_hash = result.content_hash

    facts = checks_module.measure(result.body, url=result.final_url, elapsed_ms=result.elapsed_ms)
    checks = checks_module.run_checks(facts)

    if not facts.title and facts.word_count < 20:
        return _fail(audit, "That page returned almost no readable content.")

    judgement = judge(
        audit,
        facts,
        checks,
        organization=organization or public_tools_organization(),
        provider=provider,
        requested_by=requested_by,
    )

    stored = _store(
        audit,
        facts=facts,
        checks=checks,
        judgement=judgement.output if judgement else None,
        prompt_pin=judgement.job.prompt_pin if judgement else "",
    )
    logger.info(
        "website_audit_complete",
        url=target,
        score=stored.overall_score,
        judged=stored.judged,
        failed_checks=len(stored.failed_checks),
    )
    return stored


def _fail(audit: WebsiteAudit, reason: str) -> WebsiteAudit:
    audit.status = AuditStatus.FAILED
    audit.error_reason = reason[:255]
    audit.save(update_fields=["status", "error_reason", "updated_at"])
    return audit


def _failed(*, url: str, reason: str) -> WebsiteAudit:
    return WebsiteAudit.objects.create(
        url=url[:2048], status=AuditStatus.FAILED, error_reason=reason[:255]
    )


__all__ = [
    "DEFAULT_CACHE_MINUTES",
    "cache_minutes",
    "judge",
    "public_tools_organization",
    "recent_audit",
    "run_website_audit",
]
