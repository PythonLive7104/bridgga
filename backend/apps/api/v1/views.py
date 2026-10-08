"""v1 API views."""

from __future__ import annotations

from typing import Any

from django.db import transaction
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.v1 import serializers as s
from apps.audit.models import AuditAction, AuditLog
from apps.audit.services import record_audit
from apps.billing.models import CreditEntry, Subscription
from apps.common.permissions import HasCapability, RequireOrganization
from apps.common.tenancy import unscoped
from apps.common.viewsets import TenantReadOnlyViewSet, TenantScopedViewSet
from apps.organizations import services
from apps.organizations.models import Invitation, Membership, Organization, Workspace
from apps.organizations.roles import Capability, capabilities_for


class MeView(APIView):
    """Identity and organization context for the authenticated user.

    The SPA calls this once on boot: it supplies the workspace switcher, and
    the capability list that drives which navigation items render.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(responses=s.MeSerializer)
    def get(self, request: Request) -> Response:
        from apps.common.tenant_resolution import resolve_tenant

        # Tolerates having no tenant: a user who has just signed up, or one
        # who belongs to several organizations and has not picked one, still
        # needs this response to render the organization chooser.
        membership = resolve_tenant(request)
        memberships = (
            Membership.all_objects.filter(user=request.user, is_active=True)
            .select_related("organization")
            .order_by("organization__name")
        )
        payload = {
            "user": request.user,
            "memberships": memberships,
            "active_organization": getattr(request, "organization", None),
            "active_role": membership.role if membership else None,
            "active_capabilities": sorted(capabilities_for(membership.role)) if membership else [],
        }
        return Response(s.MeSerializer(payload).data)

    @extend_schema(request=s.UserSerializer, responses=s.UserSerializer)
    def patch(self, request: Request) -> Response:
        serializer = s.UserSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class OrganizationViewSet(viewsets.ModelViewSet):
    """Organizations the caller belongs to.

    Not a ``TenantScopedViewSet``: the organization *is* the tenant, so the
    scope here is the caller's set of memberships rather than one active
    organization.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = s.OrganizationSerializer
    lookup_field = "public_id"
    lookup_url_kwarg = "public_id"
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self) -> Any:
        user = self.request.user
        if not user.is_authenticated:
            return Organization.objects.none()
        with unscoped():
            return Organization.objects.filter(
                organizations_membership_set__user=user,
                organizations_membership_set__is_active=True,
            ).distinct()

    def get_serializer_class(self) -> Any:
        if self.action == "create":
            return s.OrganizationCreateSerializer
        return s.OrganizationSerializer

    @extend_schema(
        request=s.OrganizationCreateSerializer, responses={201: s.OrganizationSerializer}
    )
    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = s.OrganizationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            organization = services.create_organization(
                name=data["name"],
                owner=request.user,
                country=data.get("country", ""),
                default_currency=data.get("default_currency") or "USD",
                timezone_name=data.get("timezone") or "UTC",
                website=data.get("website", ""),
                request=request,
            )
        except services.OrganizationError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        return Response(s.OrganizationSerializer(organization).data, status=status.HTTP_201_CREATED)

    def perform_update(self, serializer: Any) -> None:
        membership = self._require_membership(serializer.instance)
        if not membership.has_capability(Capability.ORG_MANAGE):
            self.permission_denied(self.request, message="Your role cannot edit this organization.")
        organization = serializer.save()
        record_audit(
            organization=organization,
            action=AuditAction.ORGANIZATION_UPDATED,
            actor=self.request.user,
            target=organization,
            metadata={"fields": sorted(serializer.validated_data.keys())},
            request=self.request,
        )

    def perform_destroy(self, instance: Organization) -> None:
        membership = self._require_membership(instance)
        if not membership.has_capability(Capability.ORG_DELETE):
            self.permission_denied(
                self.request, message="Only the organization owner can delete it."
            )
        # Soft stop rather than a cascade: deletion is a Phase 4 flow with a
        # grace period and integration revocation (PRD section 121).
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])
        record_audit(
            organization=instance,
            action=AuditAction.ORGANIZATION_DELETED,
            actor=self.request.user,
            target=instance,
            request=self.request,
        )

    def _require_membership(self, organization: Organization) -> Membership:
        membership = organization.membership_for(self.request.user)
        if membership is None:
            self.permission_denied(
                self.request, message="You are not a member of this organization."
            )
        return membership


class WorkspaceViewSet(TenantScopedViewSet):
    queryset = Workspace.objects.all()
    serializer_class = s.WorkspaceSerializer
    required_capability = Capability.WORKSPACE_VIEW
    write_capability = Capability.WORKSPACE_MANAGE
    search_fields = ["name"]
    ordering_fields = ["name", "created_at"]

    def perform_create(self, serializer: Any) -> None:
        workspace = serializer.save(organization=self.request.organization)
        record_audit(
            organization=self.request.organization,
            action=AuditAction.WORKSPACE_CREATED,
            actor=self.request.user,
            target=workspace,
            request=self.request,
        )

    def perform_destroy(self, instance: Workspace) -> None:
        if instance.is_default:
            raise ValidationError(
                {
                    "detail": (
                        "The default workspace cannot be deleted. Make another one default first."
                    )
                }
            )
        record_audit(
            organization=self.request.organization,
            action=AuditAction.WORKSPACE_DELETED,
            actor=self.request.user,
            target=instance,
            target_label=instance.name,
            request=self.request,
        )
        instance.delete()


class MembershipViewSet(
    TenantScopedViewSet,
):
    """Members of the active organization."""

    queryset = Membership.objects.all()
    serializer_class = s.MembershipSerializer
    required_capability = Capability.MEMBER_VIEW
    write_capability = Capability.MEMBER_MANAGE
    http_method_names = ["get", "patch", "delete", "head", "options"]
    search_fields = ["user__email", "user__first_name", "user__last_name"]

    def get_base_queryset(self) -> Any:
        return Membership.all_objects.select_related("user", "organization")

    @extend_schema(request=s.MembershipRoleSerializer, responses=s.MembershipSerializer)
    def partial_update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        target = self.get_object()
        serializer = s.MembershipRoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            updated = services.change_member_role(
                actor_membership=request.membership,
                target_membership=target,
                new_role=serializer.validated_data["role"],
                request=request,
            )
        except services.OrganizationError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        return Response(s.MembershipSerializer(updated).data)

    def perform_destroy(self, instance: Membership) -> None:
        try:
            services.remove_member(
                actor_membership=self.request.membership,
                target_membership=instance,
                request=self.request,
            )
        except services.OrganizationError as exc:
            raise ValidationError({"detail": str(exc)}) from exc


class InvitationViewSet(TenantScopedViewSet):
    queryset = Invitation.objects.all()
    serializer_class = s.InvitationSerializer
    required_capability = Capability.MEMBER_VIEW
    write_capability = Capability.MEMBER_INVITE
    http_method_names = ["get", "post", "delete", "head", "options"]

    def get_base_queryset(self) -> Any:
        return Invitation.all_objects.select_related("invited_by", "organization")

    @extend_schema(
        request=s.InvitationCreateSerializer,
        responses={201: OpenApiResponse(response=s.InvitationSerializer)},
    )
    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = s.InvitationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            invitation, raw_token = services.invite_member(
                organization=request.organization,
                inviter_membership=request.membership,
                email=serializer.validated_data["email"],
                role=serializer.validated_data["role"],
                request=request,
            )
        except services.OrganizationError as exc:
            raise ValidationError({"detail": str(exc)}) from exc

        payload = s.InvitationSerializer(invitation).data
        # The raw token is returned exactly once, on creation, so the caller
        # can deliver it. It is not retrievable afterwards.
        payload["token"] = raw_token
        payload["accept_url"] = self._accept_url(raw_token)
        return Response(payload, status=status.HTTP_201_CREATED)

    def perform_destroy(self, instance: Invitation) -> None:
        from django.utils import timezone

        instance.revoked_at = timezone.now()
        instance.save(update_fields=["revoked_at", "updated_at"])

    @staticmethod
    def _accept_url(raw_token: str) -> str:
        from django.conf import settings

        return f"{settings.FRONTEND_URL}/auth/accept-invitation?token={raw_token}"


class InvitationAcceptView(APIView):
    """Redeem an invitation. Requires authentication but no active organization."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=s.InvitationAcceptSerializer, responses={200: s.MembershipSummarySerializer}
    )
    @transaction.atomic
    def post(self, request: Request) -> Response:
        serializer = s.InvitationAcceptSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            membership = services.accept_invitation(
                raw_token=serializer.validated_data["token"],
                user=request.user,
                request=request,
            )
        except services.OrganizationError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        return Response(s.MembershipSummarySerializer(membership).data)


class AuditLogViewSet(TenantReadOnlyViewSet):
    queryset = AuditLog.objects.all()
    serializer_class = s.AuditLogSerializer
    required_capability = Capability.AUDIT_VIEW
    filterset_fields = ["action", "actor_email"]
    search_fields = ["target_label", "actor_email"]


class SubscriptionView(APIView):
    """The active organization's current subscription."""

    permission_classes = [RequireOrganization, HasCapability]
    required_capability = Capability.BILLING_VIEW

    @extend_schema(responses={200: s.SubscriptionSerializer})
    def get(self, request: Request) -> Response:
        subscription = (
            Subscription.objects.filter(organization=request.organization)
            .exclude(status="canceled")
            .select_related("plan")
            .first()
        )
        if subscription is None:
            return Response({"detail": "No active subscription."}, status=status.HTTP_404_NOT_FOUND)
        return Response(s.SubscriptionSerializer(subscription).data)


class CreditBalanceView(APIView):
    permission_classes = [RequireOrganization, HasCapability]
    required_capability = Capability.BILLING_VIEW

    @extend_schema(responses={200: s.CreditBalanceSerializer})
    def get(self, request: Request) -> Response:
        balance = CreditEntry.balance_for(request.organization)
        return Response({"balance": balance})


class CreditLedgerViewSet(TenantReadOnlyViewSet):
    queryset = CreditEntry.objects.all()
    serializer_class = s.CreditEntrySerializer
    required_capability = Capability.BILLING_VIEW
    filterset_fields = ["reason", "feature"]
