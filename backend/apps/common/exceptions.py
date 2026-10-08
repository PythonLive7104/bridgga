"""Uniform API error envelope.

Every error the API returns has the same shape, so the generated TypeScript
client can narrow on one type:

    {
      "type": "validation_error",
      "detail": "Your request could not be processed.",
      "request_id": "...",
      "errors": {"email": ["Enter a valid email address."]}
    }
"""

from __future__ import annotations

from typing import Any

import structlog
from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from apps.common.tenancy import TenantScopeError

logger = structlog.get_logger(__name__)

_TYPE_BY_STATUS = {
    status.HTTP_400_BAD_REQUEST: "validation_error",
    status.HTTP_401_UNAUTHORIZED: "authentication_required",
    status.HTTP_403_FORBIDDEN: "permission_denied",
    status.HTTP_404_NOT_FOUND: "not_found",
    status.HTTP_405_METHOD_NOT_ALLOWED: "method_not_allowed",
    status.HTTP_409_CONFLICT: "conflict",
    status.HTTP_429_TOO_MANY_REQUESTS: "rate_limited",
}


def api_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    if isinstance(exc, DjangoValidationError):
        exc = exceptions.ValidationError(detail=getattr(exc, "message_dict", exc.messages))
    elif isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, PermissionDenied):
        exc = exceptions.PermissionDenied()
    elif isinstance(exc, TenantScopeError):
        # A missing tenant scope is a server-side programming error, not a
        # client error. Log it loudly and do not explain the internals.
        logger.error("tenant_scope_missing", exc_info=exc)
        exc = exceptions.APIException("Request could not be scoped to an organization.")

    response = drf_exception_handler(exc, context)
    if response is None:
        return None

    request = context.get("request")
    request_id = getattr(request, "request_id", None)

    detail = response.data
    errors: Any = None
    if isinstance(detail, dict):
        if set(detail) == {"detail"}:
            message = str(detail["detail"])
        else:
            message = "Your request could not be processed."
            errors = detail
    elif isinstance(detail, list):
        message = "Your request could not be processed."
        errors = {"non_field_errors": detail}
    else:
        message = str(detail)

    error_type = getattr(exc, "default_code", None) or _TYPE_BY_STATUS.get(
        response.status_code, "error"
    )

    payload: dict[str, Any] = {
        "type": error_type,
        "detail": message,
        "request_id": request_id,
    }
    if errors:
        payload["errors"] = errors
    if response.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
        retry_after = response.headers.get("Retry-After") if hasattr(response, "headers") else None
        if retry_after:
            payload["retry_after"] = retry_after

    response.data = payload
    return response
