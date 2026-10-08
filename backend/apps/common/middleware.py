"""Request middleware.

Only correlation ids live here. Active-organization resolution deliberately
does not: middleware runs before DRF authenticates, so a middleware resolver
would work for session auth and silently fail for every DRF-level scheme. See
``apps.common.tenant_resolution``.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable

import structlog
from django.http import HttpRequest, HttpResponse

logger = structlog.get_logger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"


class RequestIDMiddleware:
    """Attach a correlation id to every request, response and log line.

    An inbound id is accepted so a trace can span the Next.js edge, the API and
    the Celery task it enqueues, but it is validated as a UUID first: the value
    reaches logs and response headers, so an unchecked one is a log-injection
    and header-injection vector.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request_id = self._resolve_request_id(request)
        request.request_id = request_id  # type: ignore[attr-defined]

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        started = time.monotonic()
        try:
            response = self.get_response(request)
        finally:
            # Bound context must not leak into the next request handled by
            # this worker thread, even when the view raised.
            duration_ms = round((time.monotonic() - started) * 1000, 2)

        response[REQUEST_ID_HEADER] = request_id
        logger.info(
            "http_request",
            method=request.method,
            path=request.path,
            status=response.status_code,
            duration_ms=duration_ms,
            user_id=str(getattr(getattr(request, "user", None), "public_id", "")) or None,
        )
        structlog.contextvars.clear_contextvars()
        return response

    @staticmethod
    def _resolve_request_id(request: HttpRequest) -> str:
        incoming = request.headers.get(REQUEST_ID_HEADER, "")
        try:
            return str(uuid.UUID(incoming))
        except (ValueError, AttributeError, TypeError):
            return str(uuid.uuid4())
