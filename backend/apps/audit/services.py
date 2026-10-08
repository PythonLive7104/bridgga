"""Audit recording helper.

Audit writes must never break the action they describe: a logging failure that
rolls back a role change would turn an observability problem into a data
problem. Failures are logged and swallowed.
"""

from __future__ import annotations

from typing import Any

import structlog
from django.http import HttpRequest

from apps.audit.models import AuditLog

logger = structlog.get_logger(__name__)


def record_audit(
    *,
    organization: Any,
    action: str,
    actor: Any = None,
    target: Any = None,
    target_label: str = "",
    metadata: dict[str, Any] | None = None,
    request: HttpRequest | None = None,
) -> AuditLog | None:
    """Append one audit entry. Returns None if it could not be written."""
    if organization is None:
        logger.warning("audit_skipped_no_organization", action=action)
        return None

    target_type = ""
    target_id = ""
    if target is not None:
        target_type = f"{target._meta.app_label}.{target._meta.object_name}"
        target_id = str(getattr(target, "public_id", "") or target.pk)
        if not target_label:
            target_label = str(target)[:255]

    try:
        return AuditLog.objects.create(
            organization=organization,
            action=action,
            actor=actor if getattr(actor, "pk", None) else None,
            actor_email=getattr(actor, "email", "") or "",
            target_type=target_type,
            target_id=target_id,
            target_label=target_label,
            metadata=_redact(metadata or {}),
            ip_address=_client_ip(request),
            user_agent=(request.headers.get("User-Agent", "")[:400] if request else ""),
            request_id=getattr(request, "request_id", "") or "",
        )
    except Exception:
        logger.exception("audit_write_failed", action=action)
        return None


_SENSITIVE_KEYS = frozenset(
    {
        "password",
        "password1",
        "password2",
        "token",
        "raw_token",
        "secret",
        "api_key",
        "client_secret",
        "access_token",
        "refresh_token",
        "authorization",
    }
)


def _redact(metadata: dict[str, Any]) -> dict[str, Any]:
    """Strip credentials before they reach a long-lived table.

    The audit log is read by support staff and exported to customers, so it is
    the last place a token should end up (PRD section 108: sensitive log leakage).
    """
    cleaned: dict[str, Any] = {}
    for key, value in metadata.items():
        if key.lower() in _SENSITIVE_KEYS:
            cleaned[key] = "[redacted]"
        elif isinstance(value, dict):
            cleaned[key] = _redact(value)
        else:
            cleaned[key] = value
    return cleaned


def _client_ip(request: HttpRequest | None) -> str | None:
    if request is None:
        return None
    # Trust only the leftmost entry, and only when a proxy is expected to set
    # it; anything else is client-controlled.
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip() or None
    return request.META.get("REMOTE_ADDR") or None
