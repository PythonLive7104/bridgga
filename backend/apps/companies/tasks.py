"""Celery tasks for the signal engine (PRD sections 33, 81).

Three different costs, three different queues, and the routing says which is
which (see ``CELERY_TASK_ROUTES``):

* crawling a prospect's pages is network-bound and goes to ``crawl``, where
  production applies the egress allowlist the fetcher's docstring calls for;
* detection is pure computation over stored rows and goes to ``enrich``;
* interpretation calls a paid model and goes to ``ai``, so a backlog of
  diffing cannot delay anything a customer is waiting on, and a rate limit on
  the model cannot stall the crawl.
"""

from __future__ import annotations

from typing import Any

import structlog
from celery import shared_task

from apps.common.tenancy import unscoped

logger = structlog.get_logger(__name__)


def _load_company(company_id: int) -> Any:
    from apps.companies.models import Company

    # A task has no request to inherit a tenant from, so the lookup is
    # necessarily cross-tenant and says so.
    with unscoped():
        return Company.all_objects.select_related("organization").filter(pk=company_id).first()


@shared_task(name="apps.companies.tasks.detect_company_signals", bind=True, max_retries=1)
def detect_company_signals(self: Any, company_id: int) -> int:
    """Run every deterministic detector over one company's stored evidence."""
    from apps.companies.signal_engine import run_detectors

    company = _load_company(company_id)
    if company is None:
        logger.warning("signal_task_unknown_company", company_id=company_id)
        return 0

    produced = run_detectors(company=company)

    if produced:
        # New evidence changes the opportunity score (PRD section 32), and a
        # score that does not move when its evidence moves is worse than no
        # score at all -- it looks current and is not. Queued rather than
        # called so a scoring failure cannot lose the signals just detected.
        from apps.leads.tasks import score_company_leads

        score_company_leads.delay(company.pk)

    return len(produced)


@shared_task(
    name="apps.companies.tasks.refresh_company_signals",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    retry_backoff=True,
)
def refresh_company_signals(self: Any, company_id: int) -> int:
    """Crawl the watched pages, then detect against the new snapshots.

    The two halves are one task because detection immediately after a crawl is
    the only time the before/after pair is guaranteed to exist. Splitting them
    would mean a second task racing the first.
    """
    from apps.companies.signal_engine import crawl_company_pages, run_detectors

    company = _load_company(company_id)
    if company is None:
        logger.warning("signal_task_unknown_company", company_id=company_id)
        return 0

    crawl_company_pages(company=company)
    return len(run_detectors(company=company))


@shared_task(
    name="apps.companies.tasks.interpret_company_website_change",
    bind=True,
    max_retries=1,
    default_retry_delay=120,
)
def interpret_company_website_change(self: Any, company_id: int) -> int:
    """Ask a model what a company's website change means. Costs money."""
    from apps.companies.signal_agents import interpret_website_change

    company = _load_company(company_id)
    if company is None:
        logger.warning("signal_task_unknown_company", company_id=company_id)
        return 0

    return len(interpret_website_change(company=company))


@shared_task(name="apps.companies.tasks.detect_signals_for_organization", bind=True)
def detect_signals_for_organization(self: Any, organization_id: int, limit: int = 500) -> int:
    """Fan out detection across one organization's active prospects.

    Fans out rather than looping: one long task holding a worker for an hour
    is how a queue stops draining, and a per-company task can be retried on
    its own when one site is unreachable.
    """
    from apps.companies.models import Company, CompanyStatus

    with unscoped():
        company_ids = list(
            Company.all_objects.filter(
                organization_id=organization_id, status=CompanyStatus.ACTIVE
            ).values_list("pk", flat=True)[:limit]
        )

    for company_id in company_ids:
        detect_company_signals.delay(company_id)

    logger.info(
        "signal_detection_fanned_out",
        organization_id=organization_id,
        companies=len(company_ids),
    )
    return len(company_ids)


@shared_task(name="apps.companies.tasks.prune_expired_signals", bind=True)
def prune_expired_signals(self: Any, older_than_days: int = 365) -> int:
    """Housekeeping: drop long-expired signals, keep dismissed ones."""
    from apps.companies.signal_engine import prune_signals

    return prune_signals(older_than_days=older_than_days)


__all__ = [
    "detect_company_signals",
    "detect_signals_for_organization",
    "interpret_company_website_change",
    "prune_expired_signals",
    "refresh_company_signals",
]
