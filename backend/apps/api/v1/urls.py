"""v1 URL routing.

Resource ids in paths are always UUID ``public_id`` values.

Routes carry **no trailing slash**. Next.js normalises a trailing slash away
before it applies a rewrite, so slash-terminated DRF routes end in a redirect
loop behind the proxy: Next forwards ``/api/v1/me``, Django's ``APPEND_SLASH``
answers ``301 -> /api/v1/me/``, and Next strips it again. Dropping the slash
also matches allauth's headless routes, so the whole API surface is consistent.
"""

from __future__ import annotations

from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.api.v1 import views

router = DefaultRouter(trailing_slash=False)
router.register("organizations", views.OrganizationViewSet, basename="organization")
router.register("workspaces", views.WorkspaceViewSet, basename="workspace")
router.register("members", views.MembershipViewSet, basename="membership")
router.register("invitations", views.InvitationViewSet, basename="invitation")
router.register("audit-logs", views.AuditLogViewSet, basename="auditlog")
router.register("billing/credits", views.CreditLedgerViewSet, basename="creditentry")
router.register("intelligence/snapshots", views.WebsiteSnapshotViewSet, basename="websitesnapshot")
router.register("intelligence/icps", views.ICPViewSet, basename="icp")

urlpatterns = [
    path("me", views.MeView.as_view(), name="me"),
    # Declared before the router so "accept" is not matched as a public_id.
    path(
        "invitations/accept",
        views.InvitationAcceptView.as_view(),
        name="invitation-accept",
    ),
    # A singleton: an organization has exactly one understanding of itself, so
    # the action routes sit beside it rather than under a collection id.
    path(
        "intelligence/company-profile",
        views.CompanyProfileView.as_view(),
        name="company-profile",
    ),
    path(
        "intelligence/company-profile/analyze",
        views.CompanyProfileAnalyzeView.as_view(),
        name="company-profile-analyze",
    ),
    path(
        "intelligence/company-profile/reset",
        views.CompanyProfileResetView.as_view(),
        name="company-profile-reset",
    ),
    path(
        "intelligence/company-profile/confirm",
        views.CompanyProfileConfirmView.as_view(),
        name="company-profile-confirm",
    ),
    path("billing/subscription", views.SubscriptionView.as_view(), name="subscription"),
    path("billing/balance", views.CreditBalanceView.as_view(), name="credit-balance"),
    *router.urls,
]
