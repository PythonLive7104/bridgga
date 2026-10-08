"""Root URL configuration."""

from __future__ import annotations

from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.common.views import health, readiness

urlpatterns = [
    # Liveness and readiness are unauthenticated and must stay cheap.
    path("healthz", health, name="health"),
    path("readyz", readiness, name="readiness"),
    path(f"{settings.ADMIN_URL_PREFIX}/", admin.site.urls),
    # allauth headless: session, signup, email verification, password reset,
    # social login, MFA. Browser clients use the "app" variant with cookies.
    path("auth/", include("allauth.headless.urls")),
    path("api/v1/", include(("apps.api.v1.urls", "v1"), namespace="v1")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
]
