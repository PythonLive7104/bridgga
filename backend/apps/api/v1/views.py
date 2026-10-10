"""v1 API views."""

from __future__ import annotations

from typing import Any

from django.db import transaction
from django.db.models import Q
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.v1 import serializers as s
from apps.audit.models import AuditAction, AuditLog
from apps.audit.services import record_audit
from apps.billing.models import CreditEntry, Subscription
from apps.common.pagination import PageNumberPagination
from apps.common.permissions import HasCapability, RequireOrganization
from apps.common.tenancy import unscoped
from apps.common.throttling import AnonBurstThrottle
from apps.common.viewsets import TenantReadOnlyViewSet, TenantScopedViewSet
from apps.companies import search, signal_engine
from apps.companies import tasks as company_tasks
from apps.companies.models import Company, LeadSignal, SavedSearch
from apps.intelligence import (
    agents,
    audit_agents,
    icp_agents,
    market_agents,
    research_agents,
    tasks,
)
from apps.intelligence.models import (
    ICP,
    CountryProfile,
    MarketRecommendation,
    ProfileStatus,
    ProspectResearch,
    WebsiteAudit,
    WebsiteSnapshot,
)
from apps.leads import importing, scoring
from apps.leads import services as lead_services
from apps.leads import tasks as tasks_leads
from apps.leads.models import ImportJob, ScoringProfile
from apps.leads.scoring_models import default_weights
from apps.organizations import onboarding as onboarding_state
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


class OnboardingView(APIView):
    """Where this customer has got to (PRD section 25).

    Read-only and derived: it reads the records rather than a stored counter,
    so the answer cannot be stale and the wizard self-heals if somebody
    deletes the thing a step was about. See
    ``apps.organizations.onboarding``.

    ``POST`` records that the customer has been through the path, which is
    the one part that is a decision rather than a derivation.
    """

    permission_classes = [RequireOrganization, HasCapability]
    required_capability = Capability.ORG_VIEW
    write_capability = Capability.ORG_MANAGE

    @extend_schema(responses={200: {"type": "object"}})
    def get(self, request: Request) -> Response:
        return Response(onboarding_state.onboarding_state(request.organization).as_dict())

    @extend_schema(request=None, responses={200: {"type": "object"}})
    def post(self, request: Request) -> Response:
        """Finish onboarding, whether or not every step was completed.

        Deliberately not gated on all five being done. Somebody who does not
        want market recommendations should be able to leave and use the
        product; a wizard that will not let go is a wizard people learn to
        dread.
        """
        organization = onboarding_state.mark_complete(request.organization)
        return Response(onboarding_state.onboarding_state(organization).as_dict())


class WebsiteAuditView(APIView):
    """The website sales audit (PRD sections 49 and 17).

    **Open to anybody.** Section 17 makes this a free acquisition tool, so it
    has to work for a stranger with no account: that is the whole point of
    the feature, not an oversight in the permissions.

    What stands in for authentication:

    * the SSRF-hardened fetcher, which is what makes "we will fetch any URL
      you give us" safe to offer at all (section 109);
    * an IP-keyed throttle, since there is no organization to key on;
    * a cache window, so the same URL is not crawled and billed repeatedly;
    * a ledger entry against a members-only-in-name "public tools"
      organization, so what the free tool costs is a query rather than a
      surprise on an invoice.

    A signed-in caller gets the audit attributed to their workspace, which is
    what makes the same endpoint serve the in-product feature.
    """

    authentication_classes: list = []
    permission_classes: list = []
    throttle_classes = [AnonBurstThrottle]

    @extend_schema(
        request=s.WebsiteAuditRequestSerializer,
        responses={200: s.WebsiteAuditSerializer},
        auth=[],
    )
    def post(self, request: Request) -> Response:
        serializer = s.WebsiteAuditRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user if getattr(request.user, "is_authenticated", False) else None
        organization = getattr(request, "organization", None)

        audit = audit_agents.run_website_audit(
            url=serializer.validated_data["url"],
            organization=organization,
            requested_by=user,
            email=serializer.validated_data.get("email", ""),
        )
        # 200 even for a failed audit: "that site refused the connection" is
        # an answer to the question asked, not a client error on this API.
        return Response(s.WebsiteAuditSerializer(audit).data)


class WebsiteAuditDetailView(APIView):
    """One audit by its public id, which is also its share token.

    Readable by anyone holding the link. That is the access rule the free
    tool needs -- a result somebody can send to a colleague -- and the id is
    an unguessable UUID, so having the link is the whole of the permission.
    """

    authentication_classes: list = []
    permission_classes: list = []
    throttle_classes = [AnonBurstThrottle]

    @extend_schema(responses={200: s.WebsiteAuditSerializer}, auth=[])
    def get(self, request: Request, public_id: str) -> Response:
        from django.shortcuts import get_object_or_404

        audit = get_object_or_404(WebsiteAudit, public_id=public_id)
        return Response(s.WebsiteAuditSerializer(audit).data)


class ScoringProfileView(APIView):
    """The section 32 weighting for this organization.

    A singleton: one weighting per organization, so it sits on its own path
    rather than under a collection id. Section 32 requires the weights to be
    configurable, and this is where.
    """

    permission_classes = [RequireOrganization, HasCapability]
    required_capability = Capability.PROSPECT_VIEW
    write_capability = Capability.PROSPECT_MANAGE

    def get_profile(self, request: Request) -> ScoringProfile:
        with unscoped():
            profile, _ = ScoringProfile.all_objects.get_or_create(
                organization=request.organization,
                defaults={"weights": default_weights()},
            )
        return profile

    @extend_schema(responses={200: s.ScoringProfileSerializer})
    def get(self, request: Request) -> Response:
        return Response(s.ScoringProfileSerializer(self.get_profile(request)).data)

    @extend_schema(request=s.ScoringProfileSerializer, responses={200: s.ScoringProfileSerializer})
    def patch(self, request: Request) -> Response:
        profile = self.get_profile(request)
        serializer = s.ScoringProfileSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save(updated_by=request.user)

        record_audit(
            organization=request.organization,
            action=AuditAction.SCORING_WEIGHTS_CHANGED,
            actor=request.user,
            target=profile,
            metadata={"weights": profile.resolved_weights()},
            request=request,
        )

        # Every stored score was computed under the old weighting, so leaving
        # them would mean a list sorted by one set of rules and explained by
        # another.
        tasks_leads.score_organization_leads.delay(request.organization.pk)
        return Response(serializer.data)

    @extend_schema(request=None, responses={200: s.ScoringProfileSerializer})
    def delete(self, request: Request) -> Response:
        """Restore section 32's initial weighting."""
        profile = self.get_profile(request)
        profile.weights = default_weights()
        profile.updated_by = request.user
        profile.save(update_fields=["weights", "updated_by", "updated_at"])

        record_audit(
            organization=request.organization,
            action=AuditAction.SCORING_WEIGHTS_CHANGED,
            actor=request.user,
            target=profile,
            metadata={"reset": True},
            request=request,
        )
        tasks_leads.score_organization_leads.delay(request.organization.pk)
        return Response(s.ScoringProfileSerializer(profile).data)


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


class CompanyProfileView(APIView):
    """The organization's own company profile (PRD section 26).

    A singleton rather than a collection: an organization has exactly one
    understanding of itself, so there is nothing to list and no id to address
    it by. ``GET`` creates the empty record on first call so the onboarding UI
    has something to render and bind a form to.
    """

    permission_classes = [RequireOrganization, HasCapability]
    required_capability = Capability.COMPANY_PROFILE_VIEW
    write_capability = Capability.COMPANY_PROFILE_MANAGE

    @extend_schema(responses={200: s.CompanyProfileSerializer})
    def get(self, request: Request) -> Response:
        profile = agents.get_or_create_profile(organization=request.organization)
        return Response(s.CompanyProfileSerializer(profile).data)

    @extend_schema(request=s.CompanyProfileSerializer, responses={200: s.CompanyProfileSerializer})
    def patch(self, request: Request) -> Response:
        """Edit the profile. Every AI-written field is editable (PRD section 26)."""
        profile = agents.get_or_create_profile(organization=request.organization)
        serializer = s.CompanyProfileSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        data = dict(serializer.validated_data)
        website = data.pop("website", None)
        changed = agents.apply_edits(profile=profile, data=data)

        if website is not None and website != profile.website:
            profile.website = website
            profile.save(update_fields=["website", "updated_at"])

        if changed:
            record_audit(
                organization=request.organization,
                action=AuditAction.COMPANY_PROFILE_UPDATED,
                actor=request.user,
                target=profile,
                # The field names, not the values: an audit log is read by
                # people who may not be entitled to the contents.
                metadata={"fields": changed},
                request=request,
            )

        profile.refresh_from_db()
        return Response(s.CompanyProfileSerializer(profile).data)


class CompanyProfileAnalyzeView(APIView):
    """Run the company-understanding agent against the organization's website."""

    permission_classes = [RequireOrganization, HasCapability]
    required_capability = Capability.COMPANY_PROFILE_MANAGE

    @extend_schema(
        request=s.CompanyProfileAnalyzeSerializer,
        responses={202: s.CompanyProfileSerializer},
    )
    def post(self, request: Request) -> Response:
        serializer = s.CompanyProfileAnalyzeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        website = serializer.validated_data.get("website", "")

        profile = agents.get_or_create_profile(organization=request.organization)
        if not (website or profile.website or request.organization.website):
            raise ValidationError({"website": ["Provide a website to analyse."]})

        record_audit(
            organization=request.organization,
            action=AuditAction.COMPANY_PROFILE_ANALYZED,
            actor=request.user,
            target=profile,
            metadata={"website": website or profile.website},
            request=request,
        )

        # Queued, not run inline: this crawls several pages and makes an
        # advanced-tier model call, which is far longer than a request should
        # hold open. The client polls GET for the status.
        tasks.analyze_company_website.delay(request.organization.pk, website, request.user.pk)

        profile.refresh_from_db()
        return Response(s.CompanyProfileSerializer(profile).data, status=status.HTTP_202_ACCEPTED)


class CompanyProfileResetView(APIView):
    """Restore edited fields to what the agent produced."""

    permission_classes = [RequireOrganization, HasCapability]
    required_capability = Capability.COMPANY_PROFILE_MANAGE

    @extend_schema(
        request=s.CompanyProfileResetSerializer, responses={200: s.CompanyProfileSerializer}
    )
    def post(self, request: Request) -> Response:
        serializer = s.CompanyProfileResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        profile = agents.get_or_create_profile(organization=request.organization)
        restored = agents.reset_fields(profile=profile, fields=serializer.validated_data["fields"])
        if restored:
            record_audit(
                organization=request.organization,
                action=AuditAction.COMPANY_PROFILE_UPDATED,
                actor=request.user,
                target=profile,
                metadata={"reset_fields": restored},
                request=request,
            )

        profile.refresh_from_db()
        return Response(s.CompanyProfileSerializer(profile).data)


class CompanyProfileConfirmView(APIView):
    """Onboarding step 3: the customer agrees the profile describes them."""

    permission_classes = [RequireOrganization, HasCapability]
    required_capability = Capability.COMPANY_PROFILE_MANAGE

    @extend_schema(request=None, responses={200: s.CompanyProfileSerializer})
    def post(self, request: Request) -> Response:
        profile = agents.get_or_create_profile(organization=request.organization)
        if profile.status not in {ProfileStatus.READY, ProfileStatus.CONFIRMED}:
            raise ValidationError({"detail": "Analyse the website before confirming the profile."})

        agents.confirm_profile(profile=profile)
        record_audit(
            organization=request.organization,
            action=AuditAction.COMPANY_PROFILE_CONFIRMED,
            actor=request.user,
            target=profile,
            request=request,
        )
        profile.refresh_from_db()
        return Response(s.CompanyProfileSerializer(profile).data)


class WebsiteSnapshotViewSet(TenantReadOnlyViewSet):
    """Raw fetches, kept so any claim can still be traced to its source."""

    queryset = WebsiteSnapshot.objects.all()
    serializer_class = s.WebsiteSnapshotSerializer
    required_capability = Capability.COMPANY_PROFILE_VIEW
    filterset_fields = ["status"]
    search_fields = ["requested_url", "title"]


class ICPViewSet(TenantScopedViewSet):
    """Ideal customer profiles (PRD section 27).

    A collection rather than a singleton, unlike the company profile: a real
    business sells to more than one kind of buyer, and each needs its own
    sizes, titles and signals. One is active at a time -- the default that
    prospect discovery and campaigns read.

    Reading sits with ``prospect.view`` because an ICP is what the prospect
    list means; editing sits with ``icp.manage``, because changing it changes
    what the whole workspace targets.
    """

    queryset = ICP.objects.all()
    serializer_class = s.ICPSerializer
    required_capability = Capability.PROSPECT_VIEW
    write_capability = Capability.ICP_MANAGE
    search_fields = ["name"]
    ordering_fields = ["name", "created_at"]

    def perform_update(self, serializer: Any) -> None:
        """Route edits through the service so provenance is recorded.

        Saving the serializer directly would write the fields and leave
        ``edited_fields`` untouched, and the next generation would quietly
        overwrite the customer's work.
        """
        icp = serializer.instance
        changed = icp_agents.apply_edits(icp=icp, data=dict(serializer.validated_data))
        if changed:
            record_audit(
                organization=self.request.organization,
                action=AuditAction.ICP_UPDATED,
                actor=self.request.user,
                target=icp,
                metadata={"fields": changed},
                request=self.request,
            )

    @extend_schema(request=None, responses={202: s.ICPSerializer})
    @action(detail=False, methods=["post"], url_path="generate")
    def generate(self, request: Request) -> Response:
        """Draft an ICP from the confirmed company profile."""
        if not request.membership.has_capability(Capability.ICP_MANAGE):
            self.permission_denied(request, message="Your role cannot generate an ICP.")

        icp = icp_agents.generate_icp(organization=request.organization, requested_by=request.user)
        record_audit(
            organization=request.organization,
            action=AuditAction.ICP_GENERATED,
            actor=request.user,
            target=icp,
            request=request,
        )
        return Response(s.ICPSerializer(icp).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=None, responses={200: s.ICPSerializer})
    @action(detail=True, methods=["post"], url_path="regenerate")
    def regenerate(self, request: Request, **kwargs: Any) -> Response:
        """Re-draft this ICP in place, keeping edited fields."""
        icp = self.get_object()
        if not request.membership.has_capability(Capability.ICP_MANAGE):
            self.permission_denied(request, message="Your role cannot generate an ICP.")

        icp_agents.generate_icp(
            organization=request.organization, icp=icp, requested_by=request.user
        )
        icp.refresh_from_db()
        return Response(s.ICPSerializer(icp).data)

    @extend_schema(request=s.ICPResetSerializer, responses={200: s.ICPSerializer})
    @action(detail=True, methods=["post"], url_path="reset")
    def reset(self, request: Request, **kwargs: Any) -> Response:
        """Restore edited fields to what the agent produced."""
        icp = self.get_object()
        if not request.membership.has_capability(Capability.ICP_MANAGE):
            self.permission_denied(request, message="Your role cannot edit an ICP.")

        serializer = s.ICPResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        restored = icp_agents.reset_fields(icp=icp, fields=serializer.validated_data["fields"])
        if restored:
            record_audit(
                organization=request.organization,
                action=AuditAction.ICP_UPDATED,
                actor=request.user,
                target=icp,
                metadata={"reset_fields": restored},
                request=request,
            )
        icp.refresh_from_db()
        return Response(s.ICPSerializer(icp).data)

    @extend_schema(request=None, responses={200: s.ICPSerializer})
    @action(detail=True, methods=["post"], url_path="activate")
    def activate(self, request: Request, **kwargs: Any) -> Response:
        """Make this the ICP discovery and campaigns use by default."""
        icp = self.get_object()
        if not request.membership.has_capability(Capability.ICP_MANAGE):
            self.permission_denied(request, message="Your role cannot change the active ICP.")

        icp_agents.activate(icp=icp)
        record_audit(
            organization=request.organization,
            action=AuditAction.ICP_ACTIVATED,
            actor=request.user,
            target=icp,
            target_label=icp.name,
            request=request,
        )
        icp.refresh_from_db()
        return Response(s.ICPSerializer(icp).data)


class CountryProfileViewSet(viewsets.ReadOnlyModelViewSet):
    """Seeded country intelligence (PRD section 71).

    Platform-wide rather than tenant-scoped: these are facts about a country,
    not about a customer. Readable by any authenticated user, and writable by
    nobody through the API -- they are maintained by `manage.py seed_countries`
    so that every workspace sees the same ones.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = s.CountryProfileSerializer
    queryset = CountryProfile.objects.all()
    lookup_field = "code"
    lookup_url_kwarg = "code"
    filterset_fields = ["is_launch_market", "region", "currency"]
    search_fields = ["name", "code"]


class MarketRecommendationViewSet(TenantReadOnlyViewSet):
    """Which markets to sell into, and why (PRD section 28)."""

    queryset = MarketRecommendation.objects.all()
    serializer_class = s.MarketRecommendationSerializer
    required_capability = Capability.PROSPECT_VIEW
    filterset_fields = ["fit", "is_selected"]
    ordering_fields = ["rank", "score"]

    def get_base_queryset(self) -> Any:
        return MarketRecommendation.all_objects.select_related("country")

    @extend_schema(
        request=s.MarketRecommendRequestSerializer,
        responses={200: s.MarketRecommendationSerializer(many=True)},
    )
    @action(detail=False, methods=["post"], url_path="recommend")
    def recommend(self, request: Request) -> Response:
        """Rank the seeded countries for this organization's ICP."""
        if not request.membership.has_capability(Capability.ICP_MANAGE):
            self.permission_denied(request, message="Your role cannot generate recommendations.")

        serializer = s.MarketRecommendRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            rows = market_agents.recommend_markets(
                organization=request.organization,
                include_international=serializer.validated_data["include_international"],
                requested_by=request.user,
            )
        except market_agents.MarketError as exc:
            raise ValidationError({"detail": str(exc)}) from exc

        record_audit(
            organization=request.organization,
            action=AuditAction.MARKETS_RECOMMENDED,
            actor=request.user,
            metadata={"count": len(rows)},
            request=request,
        )
        return Response(s.MarketRecommendationSerializer(rows, many=True).data)

    @extend_schema(
        request=s.MarketSelectionSerializer,
        responses={200: s.MarketRecommendationSerializer(many=True)},
    )
    @action(detail=False, methods=["post"], url_path="select")
    def select(self, request: Request) -> Response:
        """Record which markets the customer will actually work.

        The recommendation is advice; this is the decision, and prospect
        discovery reads the decision rather than the ranking.
        """
        if not request.membership.has_capability(Capability.ICP_MANAGE):
            self.permission_denied(request, message="Your role cannot choose markets.")

        serializer = s.MarketSelectionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        rows = market_agents.set_selected(
            organization=request.organization, codes=serializer.validated_data["codes"]
        )
        record_audit(
            organization=request.organization,
            action=AuditAction.MARKETS_SELECTED,
            actor=request.user,
            metadata={"codes": sorted(serializer.validated_data["codes"])},
            request=request,
        )
        return Response(s.MarketRecommendationSerializer(rows, many=True).data)


class ImportJobViewSet(TenantScopedViewSet):
    """Uploading and running a prospect list (PRD sections 51, 110).

    Upload and run are separate calls on purpose. The file is parsed on
    upload only far enough to show its headers, a suggested mapping and a few
    real rows; the customer confirms that before anything is written. Guessing
    silently is how a phone column lands in the email field for four thousand
    people, and nobody finds out until the first send.
    """

    queryset = ImportJob.objects.all()
    serializer_class = s.ImportJobSerializer
    required_capability = Capability.PROSPECT_VIEW
    write_capability = Capability.PROSPECT_MANAGE
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    http_method_names = ["get", "post", "head", "options"]

    def get_base_queryset(self) -> Any:
        return ImportJob.all_objects.select_related("source", "icp")

    @extend_schema(request=s.ImportUploadSerializer, responses={201: s.ImportJobSerializer})
    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = s.ImportUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        upload = serializer.validated_data["file"]

        icp = None
        if serializer.validated_data.get("icp"):
            icp = ICP.objects.filter(
                organization=request.organization, public_id=serializer.validated_data["icp"]
            ).first()

        source = lead_services.get_or_create_source(
            organization=request.organization,
            name=serializer.validated_data.get("source_name") or f"Import: {upload.name}"[:150],
            kind="import",
        )

        job = ImportJob.objects.create(
            organization=request.organization,
            file=upload,
            original_filename=(upload.name or "upload")[:255],
            content_type=(upload.content_type or "")[:100],
            size_bytes=upload.size,
            source=source,
            icp=icp,
            requested_by=request.user,
        )

        # Read the headers back from storage rather than the upload handler:
        # a large file was streamed to disk and the in-memory copy may be
        # exhausted, and this also proves the stored file is readable.
        try:
            with job.file.open("rb") as stream:
                found = importing.preview(stream, filename=job.original_filename)
        except importing.ImportFileError as exc:
            job.status = "failed"
            job.error_message = str(exc)[:500]
            job.save(update_fields=["status", "error_message", "updated_at"])
            raise ValidationError({"file": [str(exc)]}) from exc

        job.detected_headers = found["headers"]
        job.sample_rows = found["sample_rows"]
        job.column_mapping = found["suggested_mapping"]
        job.save(update_fields=["detected_headers", "sample_rows", "column_mapping", "updated_at"])

        return Response(s.ImportJobSerializer(job).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=s.ImportMappingSerializer, responses={202: s.ImportJobSerializer})
    @action(detail=True, methods=["post"], url_path="start")
    def start(self, request: Request, **kwargs: Any) -> Response:
        """Confirm the mapping and queue the run."""
        job = self.get_object()
        if not request.membership.has_capability(Capability.PROSPECT_MANAGE):
            self.permission_denied(request, message="Your role cannot import prospects.")

        if job.status not in {"pending", "ready", "failed"}:
            raise ValidationError({"detail": f"This import is already {job.status}."})

        serializer = s.ImportMappingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        job.column_mapping = serializer.validated_data["column_mapping"]
        job.status = "ready"
        job.error_message = ""
        job.save(update_fields=["column_mapping", "status", "error_message", "updated_at"])

        record_audit(
            organization=request.organization,
            action=AuditAction.LEADS_IMPORTED,
            actor=request.user,
            target=job,
            target_label=job.original_filename,
            metadata={"fields": sorted(job.column_mapping)},
            request=request,
        )

        tasks_leads.run_import_job.delay(job.pk)
        job.refresh_from_db()
        return Response(s.ImportJobSerializer(job).data, status=status.HTTP_202_ACCEPTED)

    @extend_schema(responses={200: {"type": "object"}})
    @action(detail=False, methods=["get"], url_path="fields")
    def fields(self, request: Request) -> Response:
        """The fields a column may be mapped to, for the mapping interface."""
        return Response(importing.CANONICAL_FIELDS)


class ProspectViewSet(TenantReadOnlyViewSet):
    """Prospect discovery (PRD sections 29, 103, 117).

    Read-only: a prospect row is assembled from a company, its contacts, its
    events and its lead, and writing to it means writing to one of those. The
    actions section 117 lists live on their own endpoints for the same reason.

    The query is kept to a fixed number of statements however many rows come
    back -- the alternative draws one page of fifty prospects with two hundred
    queries, which is the difference between the two-second target and ten.
    """

    serializer_class = s.ProspectSerializer
    queryset = Company.objects.all()
    required_capability = Capability.PROSPECT_VIEW
    # Page numbers, not cursors, and this is a correctness matter rather than
    # a preference. DRF's CursorPagination imposes its own ordering --
    # (-created_at, -id) -- on whatever queryset it is handed, because a
    # cursor is only meaningful against an ordering it controls. Applied
    # here it silently discards the relevance ranking that search.py just
    # computed, so a text search would return the newest matches rather than
    # the best ones. A ranked result set also wants a total ("31 prospects"),
    # which cursor pagination cannot give.
    pagination_class = PageNumberPagination
    # The POST actions below mutate (they queue crawls). HasCapability applies
    # this to any unsafe method, so a viewer can read prospects without being
    # able to spend the workspace's crawl budget.
    write_capability = Capability.PROSPECT_MANAGE

    @staticmethod
    def prefetched_queryset() -> Any:
        """Companies with everything a prospect row renders, in fixed queries.

        Shared with the saved-search results endpoint, so the two cannot
        diverge into one being fast and the other quietly not.
        """
        from django.db.models import Prefetch

        from apps.contacts.models import Person
        from apps.leads.models import Lead

        # Live signals, strongest first: the row shows the single best reason
        # to open it, and an expired or dismissed signal is not one.
        live_signals = LeadSignal.all_objects.active().strongest_first()
        return Company.all_objects.prefetch_related(
            Prefetch(
                "people",
                queryset=Person.all_objects.order_by("-is_decision_maker", "id"),
                to_attr="prefetched_people",
            ),
            Prefetch("signals", queryset=live_signals, to_attr="active_signals"),
            Prefetch(
                "research",
                queryset=ProspectResearch.all_objects.order_by("-researched_at", "-id"),
                to_attr="prefetched_research",
            ),
            Prefetch(
                "leads",
                queryset=Lead.all_objects.select_related("owner").order_by("-score"),
                to_attr="prefetched_leads",
            ),
        )

    def get_base_queryset(self) -> Any:
        return self.prefetched_queryset()

    def filter_queryset(self, queryset: Any) -> Any:
        filters = search.ProspectFilters.from_query_params(self.request.query_params)
        return search.search_companies(
            organization=self.request.organization, filters=filters, queryset=queryset
        )

    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        response = super().list(request, *args, **kwargs)
        # Stated rather than implied: full-text ranking is available on
        # Postgres and not on SQLite, and a caller comparing results across
        # environments should be able to see which answered.
        response.data["search_backend"] = search.search_backend()
        return response

    @extend_schema(responses={200: s.LeadSignalSerializer(many=True)})
    @action(detail=True, methods=["get"], url_path="signals")
    def signals(self, request: Request, **kwargs: Any) -> Response:
        """Every signal for one prospect, including the stale ones.

        The list view shows live signals only. Here, history is the point: a
        rep deciding whether to call wants to know that this company was
        hiring for the same role six months ago too.
        """
        company = self.get_object()
        include_stale = str(request.query_params.get("include_stale", "")).lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        queryset = LeadSignal.all_objects.filter(company=company)
        if not include_stale:
            queryset = queryset.active()
        return Response(s.LeadSignalSerializer(queryset.strongest_first(), many=True).data)

    @extend_schema(responses={200: {"type": "object"}})
    @action(detail=True, methods=["get"], url_path="score")
    def score(self, request: Request, **kwargs: Any) -> Response:
        """The opportunity score with its explanation (PRD sections 32, 119).

        Computed on read rather than served from the stored breakdown. It is
        pure database reads, and the alternative is showing a stale
        explanation beside a number the customer just changed the weights
        for. The stored copy on the lead is what lists and filters sort by;
        this is the answer to "why".
        """
        company = self.get_object()
        lead = (
            company.leads.select_related("icp").order_by("-score").first()
            if hasattr(company, "leads")
            else None
        )
        result = scoring.score_prospect(company, icp=lead.icp if lead else None)

        payload = result.payload()
        payload["company"] = {"id": str(company.public_id), "name": company.name}
        payload["lead"] = str(lead.public_id) if lead else None
        # Stated, because the two can differ: the stored score is what the
        # table sorted by, and if it is behind, a reader should know rather
        # than wonder why the number moved when they opened the panel.
        payload["stored_score"] = lead.score if lead else None
        return Response(payload)

    @extend_schema(request=None, responses={202: {"type": "object"}})
    @action(detail=True, methods=["post"], url_path="rescore")
    def rescore(self, request: Request, **kwargs: Any) -> Response:
        """Recompute and store this prospect's score now."""
        company = self.get_object()
        leads = list(company.leads.select_related("icp", "organization").all())
        if not leads:
            raise ValidationError(
                {"detail": ["This company is not a lead yet, so there is no score to store."]}
            )

        for lead in leads:
            scoring.score_lead(lead)

        return Response({"status": "scored", "leads": len(leads)})

    @extend_schema(request=None, responses={202: {"type": "object"}})
    @action(detail=True, methods=["post"], url_path="detect-signals")
    def detect_signals(self, request: Request, **kwargs: Any) -> Response:
        """Re-crawl this prospect's watched pages and detect against them.

        Queued, not inline: it makes several outbound fetches, which is far
        longer than a request should hold open.
        """
        company = self.get_object()
        company_tasks.refresh_company_signals.delay(company.pk)
        return Response({"status": "queued"}, status=status.HTTP_202_ACCEPTED)

    @extend_schema(
        request=None,
        responses={200: s.ProspectResearchSerializer, 202: s.ProspectResearchSerializer},
    )
    @action(detail=True, methods=["get", "post", "patch"], url_path="research")
    def research(self, request: Request, **kwargs: Any) -> Response:
        """The sales brief for one prospect (PRD sections 34, 35).

        GET reads it, POST queues a fresh run, PATCH records a human's
        corrections. One route because they are three verbs on one resource,
        and a brief that lived at three paths would be three things to keep in
        step.
        """
        company = self.get_object()
        existing = list(company.research.select_related("icp").order_by("-researched_at"))

        if request.method == "GET":
            if not existing:
                return Response(
                    {"detail": "This prospect has not been researched yet."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            return Response(s.ProspectResearchSerializer(existing[0]).data)

        if request.method == "PATCH":
            if not existing:
                raise ValidationError({"detail": ["There is no brief to edit yet."]})
            brief = existing[0]
            changed = research_agents.apply_edits(research=brief, data=request.data)
            brief.refresh_from_db()
            return Response({**s.ProspectResearchSerializer(brief).data, "changed_fields": changed})

        # POST: queued, because this is an advanced-tier model call over a
        # large context and far longer than a request should be held open.
        tasks.research_prospect.delay(
            company.pk,
            existing[0].icp_id if existing else None,
            request.user.pk,
        )
        return Response({"status": "queued"}, status=status.HTTP_202_ACCEPTED)

    @extend_schema(request=s.ResearchResetSerializer, responses={200: s.ProspectResearchSerializer})
    @action(detail=True, methods=["post"], url_path="research/reset")
    def research_reset(self, request: Request, **kwargs: Any) -> Response:
        """Drop a human's edits and restore what the agent wrote."""
        company = self.get_object()
        brief = company.research.order_by("-researched_at").first()
        if brief is None:
            raise ValidationError({"detail": ["There is no brief to reset."]})

        serializer = s.ResearchResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        restored = research_agents.reset_fields(
            research=brief, fields=serializer.validated_data["fields"]
        )
        brief.refresh_from_db()
        return Response({**s.ProspectResearchSerializer(brief).data, "restored_fields": restored})

    @extend_schema(responses={200: {"type": "object"}})
    @action(detail=False, methods=["get"], url_path="facets")
    def facets(self, request: Request) -> Response:
        """The values actually present, for building the filter controls.

        Offering every country in the world when a workspace holds prospects
        in three is a filter nobody can use.
        """
        from django.db.models import Count

        base = Company.all_objects.filter(organization=request.organization).exclude(
            status__in=["duplicate", "disqualified"]
        )

        def top(field_name: str, limit: int = 30) -> list[dict]:
            return [
                {"value": row[field_name], "count": row["count"]}
                for row in base.exclude(**{field_name: ""})
                .values(field_name)
                .annotate(count=Count("id"))
                .order_by("-count")[:limit]
            ]

        return Response(
            {
                "countries": top("country"),
                "industries": top("industry"),
                "employee_ranges": top("employee_range"),
                "search_backend": search.search_backend(),
            }
        )


class SignalViewSet(TenantReadOnlyViewSet):
    """The buying-signal feed (PRD section 33).

    Read-only with one exception, ``dismiss``, because a signal is an
    observation and the only thing a person should be able to do to an
    observation is disagree with it. Editing one would destroy the evidence
    trail that makes it worth anything.
    """

    serializer_class = s.LeadSignalSerializer
    queryset = LeadSignal.objects.all()
    required_capability = Capability.PROSPECT_VIEW
    write_capability = Capability.PROSPECT_MANAGE
    # Same reason as the prospect list: the feed is ordered by strength, and
    # cursor pagination would reorder it by creation date.
    pagination_class = PageNumberPagination

    def get_base_queryset(self) -> Any:
        return LeadSignal.all_objects.select_related("company")

    def filter_queryset(self, queryset: Any) -> Any:
        params = self.request.query_params

        def flag(name: str) -> bool:
            return str(params.get(name, "")).lower() in {"1", "true", "yes", "on"}

        # Live signals by default: someone opening the feed wants the reasons
        # to call today, not an archive. The two flags are independent rather
        # than nested, so asking for dismissed signals does not also require
        # asking for expired ones -- "show me what my team rejected" is a
        # question about the detectors, and it has nothing to do with age.
        from django.utils import timezone

        if not flag("include_expired"):
            queryset = queryset.filter(expires_at__gt=timezone.now())
        if not flag("include_dismissed"):
            queryset = queryset.filter(dismissed_at__isnull=True)

        types = [
            part.strip()
            for raw in params.getlist("type")
            for part in str(raw).split(",")
            if part.strip()
        ]
        if types:
            queryset = queryset.of_type(types)

        if company := params.get("company"):
            queryset = queryset.filter(company__public_id=company)

        try:
            if days := int(params.get("days") or 0):
                queryset = queryset.detected_within(days)
        except (TypeError, ValueError):
            pass

        return queryset.strongest_first()

    @extend_schema(request=s.SignalDismissSerializer, responses={200: s.LeadSignalSerializer})
    @action(detail=True, methods=["post"], url_path="dismiss")
    def dismiss(self, request: Request, **kwargs: Any) -> Response:
        """Mark a signal as not relevant. Kept, not deleted."""
        signal = self.get_object()
        serializer = s.SignalDismissSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reason = serializer.validated_data.get("reason", "")

        signal_engine.dismiss_signal(signal=signal, user=request.user, reason=reason)
        record_audit(
            organization=request.organization,
            action=AuditAction.SIGNAL_DISMISSED,
            actor=request.user,
            target=signal,
            metadata={
                "signal_type": signal.signal_type,
                "detector": signal.detector,
                "reason": reason,
            },
            request=request,
        )
        return Response(s.LeadSignalSerializer(signal).data)

    @extend_schema(responses={200: {"type": "object"}})
    @action(detail=False, methods=["get"], url_path="summary")
    def summary(self, request: Request) -> Response:
        """Live signal counts by type, for the feed's filters.

        Built from what is present, like the prospect facets: offering a
        filter for a signal type nobody has is a filter that returns nothing.
        """
        from django.db.models import Count

        rows = (
            LeadSignal.all_objects.filter(organization=request.organization)
            .active()
            .values("signal_type")
            .annotate(count=Count("id"))
            .order_by("-count")
        )
        counts = [{"value": row["signal_type"], "count": row["count"]} for row in rows]
        return Response({"types": counts, "total": sum(row["count"] for row in counts)})


class SavedSearchViewSet(TenantScopedViewSet):
    """Named prospect searches (PRD section 29).

    The filters are stored, never the results: running it again should surface
    what matches today, not what matched when it was saved.
    """

    queryset = SavedSearch.objects.all()
    serializer_class = s.SavedSearchSerializer
    required_capability = Capability.PROSPECT_VIEW
    write_capability = Capability.PROSPECT_MANAGE
    search_fields = ["name"]

    def get_base_queryset(self) -> Any:
        queryset = SavedSearch.all_objects.select_related("created_by")
        user = self.request.user
        # A private search belongs to whoever made it; a shared one is the
        # team's definition of a good prospect and everyone sees it.
        #
        # The third case is one with no creator at all. `created_by` is
        # SET_NULL, so a private search outlives the person who made it, and
        # without this it would be nobody's and therefore invisible to
        # everyone -- a row that cannot be read, run or deleted. It is not
        # private to anyone any more, so the workspace keeps it.
        return queryset.filter(Q(is_shared=True) | Q(created_by=user) | Q(created_by__isnull=True))

    def perform_create(self, serializer: Any) -> None:
        serializer.save(organization=self.request.organization, created_by=self.request.user)

    @extend_schema(responses={200: s.ProspectSerializer(many=True)})
    @action(detail=True, methods=["get"], url_path="results")
    def results(self, request: Request, **kwargs: Any) -> Response:
        """Run the saved filters now."""
        from django.utils import timezone

        saved = self.get_object()
        # Unknown keys are dropped rather than raising: a saved search written
        # against an older filter set should still run, minus the part that no
        # longer exists.
        known = search.ProspectFilters.__dataclass_fields__
        filters = search.ProspectFilters(
            **{key: value for key, value in (saved.filters or {}).items() if key in known}
        )

        # Borrow the prospect view's prefetches rather than querying plainly:
        # the serializer reads contacts, events and leads off each row, and
        # without them this draws a page in two hundred queries.
        queryset = search.search_companies(
            organization=request.organization,
            filters=filters,
            queryset=ProspectViewSet.prefetched_queryset(),
        )

        saved.last_run_at = timezone.now()
        saved.last_result_count = queryset.count()
        saved.save(update_fields=["last_run_at", "last_result_count", "updated_at"])

        page = self.paginate_queryset(queryset)
        serializer = s.ProspectSerializer(page or queryset, many=True)
        return (
            self.get_paginated_response(serializer.data)
            if page is not None
            else Response(serializer.data)
        )
