"""v1 serializers.

Serializers validate and shape; they do not contain business rules. Anything
with a rule behind it delegates to a service module.

No serializer exposes a primary key. ``public_id`` is the only identifier that
crosses the API boundary.
"""

from __future__ import annotations

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.accounts.models import User
from apps.ai.schemas import SignalType
from apps.audit.models import AuditLog
from apps.billing.models import CreditEntry, Plan, Subscription
from apps.intelligence.models import ICP, CompanyProfile, WebsiteSnapshot
from apps.organizations.models import Invitation, Membership, Organization, Workspace
from apps.organizations.roles import Role, capabilities_for


class UserSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    full_name = serializers.CharField(source="get_full_name", read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "locale",
            "timezone",
            "date_joined",
        ]
        read_only_fields = ["id", "email", "date_joined"]


class OrganizationSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)

    class Meta:
        model = Organization
        fields = [
            "id",
            "name",
            "slug",
            "country",
            "default_currency",
            "timezone",
            "website",
            "created_at",
        ]
        read_only_fields = ["id", "slug", "created_at"]


class OrganizationCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    country = serializers.CharField(max_length=2, required=False, allow_blank=True)
    default_currency = serializers.CharField(max_length=3, required=False, allow_blank=True)
    timezone = serializers.CharField(max_length=64, required=False, allow_blank=True)
    website = serializers.URLField(required=False, allow_blank=True)


class WorkspaceSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)

    class Meta:
        model = Workspace
        fields = ["id", "name", "slug", "is_default", "country", "timezone", "created_at"]
        read_only_fields = ["id", "slug", "created_at"]


class MembershipSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    user = UserSerializer(read_only=True)
    capabilities = serializers.SerializerMethodField()

    class Meta:
        model = Membership
        fields = ["id", "user", "role", "is_active", "joined_at", "capabilities"]
        read_only_fields = ["id", "user", "is_active", "joined_at"]

    def get_capabilities(self, obj: Membership) -> list[str]:
        return sorted(capabilities_for(obj.role))


class MembershipRoleSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=Role.choices)


class MembershipSummarySerializer(serializers.ModelSerializer):
    """The membership list returned by /me, used by the workspace switcher."""

    organization = OrganizationSerializer(read_only=True)
    capabilities = serializers.SerializerMethodField()

    class Meta:
        model = Membership
        fields = ["organization", "role", "capabilities"]

    def get_capabilities(self, obj: Membership) -> list[str]:
        return sorted(capabilities_for(obj.role))


class InvitationSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    invited_by = serializers.EmailField(source="invited_by.email", read_only=True, default=None)
    is_pending = serializers.BooleanField(read_only=True)

    class Meta:
        model = Invitation
        fields = [
            "id",
            "email",
            "role",
            "invited_by",
            "expires_at",
            "accepted_at",
            "revoked_at",
            "is_pending",
            "created_at",
        ]
        # token_hash is deliberately absent: it never leaves the database.
        read_only_fields = ["id", "expires_at", "accepted_at", "revoked_at", "created_at"]


class InvitationCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=Role.choices, default=Role.VIEWER)


class InvitationAcceptSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=200, trim_whitespace=True)


class AuditLogSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)

    class Meta:
        model = AuditLog
        fields = [
            "id",
            "action",
            "actor_email",
            "target_type",
            "target_id",
            "target_label",
            "metadata",
            "ip_address",
            "request_id",
            "created_at",
        ]
        read_only_fields = fields


class PlanSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)

    class Meta:
        model = Plan
        fields = [
            "id",
            "tier",
            "name",
            "description",
            "monthly_price_minor",
            "currency",
            "included_credits",
            "max_seats",
            "max_workspaces",
            "max_prospects_per_month",
        ]
        read_only_fields = fields


class SubscriptionSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    plan = PlanSerializer(read_only=True)

    class Meta:
        model = Subscription
        fields = [
            "id",
            "plan",
            "status",
            "seats",
            "currency",
            "current_period_start",
            "current_period_end",
            "trial_ends_at",
        ]
        read_only_fields = fields


class CreditEntrySerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)

    class Meta:
        model = CreditEntry
        fields = ["id", "amount", "reason", "description", "feature", "created_at"]
        read_only_fields = fields


class CreditBalanceSerializer(serializers.Serializer):
    balance = serializers.IntegerField(read_only=True)


class MeSerializer(serializers.Serializer):
    """Everything the SPA needs on boot: identity, orgs, and active context."""

    user = UserSerializer(read_only=True)
    memberships = MembershipSummarySerializer(many=True, read_only=True)
    active_organization = OrganizationSerializer(read_only=True, allow_null=True)
    active_role = serializers.CharField(read_only=True, allow_null=True)
    active_capabilities = serializers.ListField(child=serializers.CharField(), read_only=True)


class WebsiteSnapshotSerializer(serializers.ModelSerializer):
    """The evidence trail behind a profile (PRD section 58)."""

    id = serializers.UUIDField(source="public_id", read_only=True)

    class Meta:
        model = WebsiteSnapshot
        fields = [
            "id",
            "requested_url",
            "final_url",
            "status",
            "status_code",
            "error_reason",
            "title",
            "fetched_at",
        ]
        read_only_fields = fields


class CompanyProfileSerializer(serializers.ModelSerializer):
    """The company profile, with provenance attached to each field.

    ``fields_meta`` is the part that matters to the UI. Every AI-written field
    reports whether a human has edited it and what the agent originally said,
    which is what lets the interface show "edited — revert to the AI version"
    rather than presenting an edited field and a generated one identically.
    """

    id = serializers.UUIDField(source="public_id", read_only=True)
    sources = WebsiteSnapshotSerializer(source="source_snapshots", many=True, read_only=True)
    fields_meta = serializers.SerializerMethodField()

    class Meta:
        model = CompanyProfile
        fields = [
            "id",
            "website",
            "company_name",
            "one_line_summary",
            "industry",
            "business_model",
            "value_proposition",
            "pricing_summary",
            "products",
            "target_customers",
            "use_cases",
            "pain_points_solved",
            "geographies",
            "buyer_personas",
            "competitors",
            "evidence",
            "unknowns",
            "confidence",
            "status",
            "analysis_error",
            "prompt_pin",
            "last_analyzed_at",
            "confirmed_at",
            "edited_fields",
            "sources",
            "fields_meta",
            "created_at",
            "updated_at",
        ]
        # The editable surface is exactly AI_FIELDS. Status, evidence and
        # provenance are the system's account of what happened and are not
        # writable: a client that could set `status` could mark an unanalysed
        # profile confirmed.
        read_only_fields = [
            field
            for field in fields
            if field not in CompanyProfile.AI_FIELDS and field != "website"
        ]

    @extend_schema_field(
        {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "properties": {
                    "edited": {"type": "boolean"},
                    "ai_value": {},
                },
            },
        }
    )
    def get_fields_meta(self, obj: CompanyProfile) -> dict[str, dict]:
        return {
            field: {"edited": obj.was_edited(field), "ai_value": obj.ai_value_for(field)}
            for field in CompanyProfile.AI_FIELDS
        }


class CompanyProfileAnalyzeSerializer(serializers.Serializer):
    website = serializers.URLField(required=False, allow_blank=True, max_length=2048)


class CompanyProfileResetSerializer(serializers.Serializer):
    """Which edited fields to restore to the agent's version."""

    fields = serializers.ListField(
        child=serializers.ChoiceField(choices=[(f, f) for f in CompanyProfile.AI_FIELDS]),
        allow_empty=False,
    )


class ICPSerializer(serializers.ModelSerializer):
    """An ideal customer profile, with the same per-field provenance as the profile."""

    id = serializers.UUIDField(source="public_id", read_only=True)
    fields_meta = serializers.SerializerMethodField()

    class Meta:
        model = ICP
        fields = [
            "id",
            "name",
            "industries",
            "countries",
            "employee_range",
            "business_size",
            "business_models",
            "technologies",
            "growth_stage",
            "job_titles",
            "departments",
            "seniority",
            "responsibilities",
            "pain_signals",
            "rationale",
            "evidence",
            "confidence",
            "status",
            "generation_error",
            "prompt_pin",
            "is_active",
            "edited_fields",
            "fields_meta",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [f for f in fields if f not in ICP.AI_FIELDS]

    @extend_schema_field(
        {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "properties": {"edited": {"type": "boolean"}, "ai_value": {}},
            },
        }
    )
    def get_fields_meta(self, obj: ICP) -> dict[str, dict]:
        return obj.fields_meta()

    def validate_pain_signals(self, value: list) -> list:
        """Keep the signal vocabulary closed on the way in.

        A free-text type would be accepted here and then never match anything
        the signal engine detects, which fails silently and much later.
        """
        valid = {member.value for member in SignalType}
        for entry in value:
            if not isinstance(entry, dict):
                raise serializers.ValidationError("Each signal must be an object.")
            if entry.get("type") not in valid:
                raise serializers.ValidationError(
                    f"Unknown signal type {entry.get('type')!r}. "
                    f"Choose one of: {', '.join(sorted(valid))}."
                )
            if not entry.get("description"):
                raise serializers.ValidationError("Each signal needs a description.")
        return value


class ICPResetSerializer(serializers.Serializer):
    fields = serializers.ListField(
        child=serializers.ChoiceField(choices=[(f, f) for f in ICP.AI_FIELDS]),
        allow_empty=False,
    )
