"""Health endpoints.

``/healthz`` answers "is this process alive" and must never touch a dependency,
or a database blip will cause the orchestrator to kill healthy containers.
``/readyz`` answers "can this process serve traffic" and does check them.
"""

from __future__ import annotations

from typing import Any

from django.db import connection
from django.http import HttpRequest, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET


@require_GET
@never_cache
def health(_request: HttpRequest) -> JsonResponse:
    return JsonResponse({"status": "ok"})


@require_GET
@never_cache
def readiness(_request: HttpRequest) -> JsonResponse:
    checks: dict[str, Any] = {}
    ok = True

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {exc.__class__.__name__}"
        ok = False

    try:
        from django.core.cache import cache

        cache.set("readyz", "1", timeout=5)
        checks["cache"] = "ok" if cache.get("readyz") == "1" else "error: readback failed"
        ok = ok and checks["cache"] == "ok"
    except Exception as exc:
        checks["cache"] = f"error: {exc.__class__.__name__}"
        ok = False

    return JsonResponse(
        {"status": "ok" if ok else "degraded", "checks": checks}, status=200 if ok else 503
    )
