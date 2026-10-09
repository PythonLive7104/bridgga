"""Celery tasks for lead imports.

Routed to the ``enrich`` queue (see CELERY_TASK_ROUTES). An import of tens of
thousands of rows is minutes of work, which is far longer than a request can
be held open, and it must not sit in front of outbound message delivery.
"""

from __future__ import annotations

import structlog
from celery import shared_task

from apps.common.tenancy import unscoped

logger = structlog.get_logger(__name__)


@shared_task(
    name="apps.leads.tasks.run_import_job",
    bind=True,
    # No automatic retry. The pipeline records row failures itself and is not
    # idempotent in a way that makes a blind re-run safe: a second attempt
    # would re-count every row it already imported.
    max_retries=0,
)
def run_import_job(self, job_id: int) -> str | None:
    from apps.leads.import_models import ImportJob
    from apps.leads.import_pipeline import run_import

    with unscoped():
        job = (
            ImportJob.all_objects.select_related("organization", "source", "icp")
            .filter(pk=job_id)
            .first()
        )

    if job is None:
        logger.warning("import_task_unknown_job", job_id=job_id)
        return None

    run_import(job=job)
    return str(job.public_id)
