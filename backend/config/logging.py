"""structlog configuration.

Emits one JSON object per line on stdout so the log shipper in any environment
can parse it without a regex. Every record carries the request id injected by
``apps.common.middleware.RequestIDMiddleware``, which is what makes an API
error, a Celery failure and a provider failure joinable (PRD section 105).
"""

from __future__ import annotations

import logging
from typing import Any

import structlog

SHARED_PROCESSORS: list[Any] = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_logger_name,
    structlog.stdlib.add_log_level,
    structlog.processors.TimeStamper(fmt="iso", utc=True),
    structlog.processors.StackInfoRenderer(),
    structlog.processors.UnicodeDecoder(),
]


def configure_structlog() -> None:
    structlog.configure(
        processors=[
            *SHARED_PROCESSORS,
            structlog.processors.format_exc_info,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def logging_config(level: str = "INFO") -> dict[str, Any]:
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {
                "()": structlog.stdlib.ProcessorFormatter,
                "processor": structlog.processors.JSONRenderer(),
                "foreign_pre_chain": SHARED_PROCESSORS,
            },
            "console": {
                "()": structlog.stdlib.ProcessorFormatter,
                "processor": structlog.dev.ConsoleRenderer(colors=False),
                "foreign_pre_chain": SHARED_PROCESSORS,
            },
        },
        "handlers": {
            "stdout": {
                "class": "logging.StreamHandler",
                "formatter": "json",
            },
        },
        "root": {"handlers": ["stdout"], "level": level},
        "loggers": {
            # Request logging is our middleware's job; Django's own access log
            # would duplicate it.
            "django.server": {"handlers": ["stdout"], "level": "WARNING", "propagate": False},
            "django.request": {"handlers": ["stdout"], "level": "ERROR", "propagate": False},
            "django.db.backends": {"handlers": ["stdout"], "level": "WARNING", "propagate": False},
            "celery": {"handlers": ["stdout"], "level": level, "propagate": False},
        },
    }


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)


__all__ = ["configure_structlog", "get_logger", "logging_config"]


# Silence the noisy "log unhandled" path during tests.
logging.captureWarnings(True)
