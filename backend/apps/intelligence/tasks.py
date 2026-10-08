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
