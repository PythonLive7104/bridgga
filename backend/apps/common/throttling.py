"""Rate limiting (PRD section 74).

Throttles key on the organization, not the user, when one is active: a tenant
should not be able to multiply its own quota by inviting more seats, and one
noisy tenant should not consume another's budget.

Type-only imports are guarded because DRF resolves ``DEFAULT_THROTTLE_CLASSES``
while ``rest_framework.views`` is still being imported; a module-level
``from rest_framework.views import APIView`` here is a circular import.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rest_framework.throttling import SimpleRateThrottle

if TYPE_CHECKING:
    from rest_framework.request import Request
    from rest_framework.views import APIView


class _OrganizationScopedThrottle(SimpleRateThrottle):
    def get_cache_key(self, request: Request, view: APIView) -> str | None:
        organization = getattr(request, "organization", None)
        if organization is not None:
            identifier = f"org:{organization.public_id}"
        elif request.user and request.user.is_authenticated:
            identifier = f"user:{request.user.pk}"
        else:
            ident = self.get_ident(request)
            if not ident:
                return None
            identifier = f"ip:{ident}"
        return self.cache_format % {"scope": self.scope, "ident": identifier}


class BurstRateThrottle(_OrganizationScopedThrottle):
    """Absorbs short spikes, e.g. a dashboard loading many widgets at once."""

    scope = "burst"


class SustainedRateThrottle(_OrganizationScopedThrottle):
    """Caps daily volume so a runaway script cannot exhaust the API."""

    scope = "sustained"


class AnonBurstThrottle(SimpleRateThrottle):
    """For unauthenticated endpoints: the free tools and public forms."""

    scope = "anon_burst"

    def get_cache_key(self, request: Request, view: APIView) -> str | None:
        ident = self.get_ident(request)
        if not ident:
            return None
        return self.cache_format % {"scope": self.scope, "ident": ident}
