"""Celery application.

Queue layout matches PRD section 81: a long website crawl or an expensive AI
research job must never sit in front of outbound message delivery.
"""

from __future__ import annotations

import os

from celery import Celery
from celery.signals import setup_logging
from kombu import Queue

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("palatial")
app.config_from_object("django.conf:settings", namespace="CELERY")

app.conf.task_queues = [
    Queue("default"),
    Queue("crawl"),
    Queue("enrich"),
    Queue("ai"),
    Queue("send"),
    Queue("analytics"),
]

app.autodiscover_tasks()


@setup_logging.connect
def configure_celery_logging(**_kwargs: object) -> None:
    """Let Django's structlog config own logging instead of Celery's."""
    from logging.config import dictConfig

    from django.conf import settings

    dictConfig(settings.LOGGING)


@app.task(bind=True, name="config.debug_task")
def debug_task(self) -> str:
    return f"request: {self.request!r}"
