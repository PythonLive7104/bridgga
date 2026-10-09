"""Celery tasks for website analysis.

Routed to the dedicated ``crawl`` queue (see CELERY_TASK_ROUTES). Crawling is
the only code path that makes outbound requests to addresses a customer chose,
so isolating it on its own worker is what lets production apply a
network-level egress allowlist -- the mitigation for the DNS-rebinding window
documented in apps.intelligence.fetcher.
"""

from __future__ import annotations

import structlog
from celery import shared_task

from apps.common.tenancy import unscoped
from apps.intelligence.services import capture_snapshot

logger = structlog.get_logger(__name__)


@shared_task(
    name="apps.intelligence.tasks.capture_website_snapshot",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    # A crawl is cheap to repeat and the snapshot row records each attempt, so
    # retrying is safe. Failures are stored, not raised, so retries only happen
    # for genuinely unexpected errors.
    autoretry_for=(ConnectionError,),
    retry_backoff=True,
)
def capture_website_snapshot(self, organization_id: int, url: str) -> str | None:
    """Fetch and store one website snapshot for an organization."""
    from apps.organizations.models import Organization

    # A task has no request to inherit a tenant from, so it states the tenant
    # it acts for explicitly. The lookup itself is necessarily cross-tenant.
    with unscoped():
        organization = Organization.objects.filter(pk=organization_id).first()

    if organization is None:
        logger.warning("snapshot_task_unknown_organization", organization_id=organization_id)
        return None

    snapshot = capture_snapshot(organization=organization, url=url)
    return str(snapshot.public_id)


@shared_task(
    name="apps.intelligence.tasks.analyze_company_website",
    bind=True,
    max_retries=1,
    default_retry_delay=60,
)
def analyze_company_website(
    self, organization_id: int, url: str = "", requested_by_id: int | None = None
) -> str | None:
    """Run the company-understanding agent for one organization.

    Routed to the ``ai`` queue rather than ``crawl``: it does fetch pages, but
    the expensive and rate-limited part is the model call, and queueing it
    behind a crawl backlog would make onboarding feel broken.

    Retries are capped at one. The agent records its own failures on the
    profile, so a retry only helps for a genuinely transient error, and a
    repeated model call is not free.
    """
    from apps.intelligence.agents import analyze_company
    from apps.organizations.models import Organization

    with unscoped():
        organization = Organization.objects.filter(pk=organization_id).first()
        requested_by = None
        if requested_by_id:
            from django.contrib.auth import get_user_model

            requested_by = get_user_model().objects.filter(pk=requested_by_id).first()

    if organization is None:
        logger.warning("analysis_task_unknown_organization", organization_id=organization_id)
        return None

    profile = analyze_company(organization=organization, url=url, requested_by=requested_by)
    return str(profile.public_id)


@shared_task(
    name="apps.intelligence.tasks.research_prospect",
    bind=True,
    max_retries=1,
    default_retry_delay=120,
)
def research_prospect(
    self, company_id: int, icp_id: int | None = None, requested_by_id: int | None = None
) -> str | None:
    """Research one prospect (PRD section 34).

    Routed to the ``ai`` queue, not ``crawl``: it makes no outbound requests
    at all. Everything it reads -- signals, their quoted evidence, the company
    record, the latest page text -- is already stored, and re-fetching would
    be slower, costlier and no more current.
    """
    from apps.companies.models import Company
    from apps.intelligence.models import ICP
    from apps.intelligence.research_agents import research_company

    with unscoped():
        company = Company.all_objects.select_related("organization").filter(pk=company_id).first()
        icp = ICP.all_objects.filter(pk=icp_id).first() if icp_id else None
        requested_by = None
        if requested_by_id:
            from django.contrib.auth import get_user_model

            requested_by = get_user_model().objects.filter(pk=requested_by_id).first()

    if company is None:
        logger.warning("research_task_unknown_company", company_id=company_id)
        return None

    research = research_company(company=company, icp=icp, requested_by=requested_by)
    return str(research.public_id)


@shared_task(name="apps.intelligence.tasks.research_top_prospects", bind=True)
def research_top_prospects(
    self, organization_id: int, limit: int = 20, min_score: int | None = None
) -> int:
    """Research the best-scoring leads in one organization.

    Section 34 scopes research to high-value prospects, and the threshold is
    why: this is an advanced-tier model call per company, so running it across
    a freshly imported list of ten thousand would cost more than the list did.
    A human asking for one prospect by hand is never gated -- they have
    already decided it is worth it.
    """
    from django.conf import settings

    from apps.leads.models import Lead

    threshold = min_score if min_score is not None else getattr(settings, "RESEARCH_MIN_SCORE", 60)

    with unscoped():
        rows = list(
            Lead.all_objects.filter(organization_id=organization_id, score__gte=threshold)
            .order_by("-score")
            .values_list("company_id", "icp_id")[:limit]
        )

    for company_id, icp_id in rows:
        research_prospect.delay(company_id, icp_id)

    logger.info(
        "research_fanned_out",
        organization_id=organization_id,
        prospects=len(rows),
        min_score=threshold,
    )
    return len(rows)
