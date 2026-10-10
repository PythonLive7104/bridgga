"""v1 serializers.

Serializers validate and shape; they do not contain business rules. Anything
with a rule behind it delegates to a service module.

No serializer exposes a primary key. ``public_id`` is the only identifier that
crosses the API boundary.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.accounts.models import User
from apps.ai.schemas import SignalType
from apps.audit.models import AuditLog
from apps.billing.models import CreditEntry, Plan, Subscription
from apps.companies.models import Company, CompanyEvent, LeadSignal, SavedSearch
from apps.contacts.models import Person
from apps.intelligence.models import (
    ICP,
    CompanyProfile,
    CountryProfile,
    MarketRecommendation,
    ProspectResearch,
    WebsiteAudit,
    WebsiteSnapshot,
)
from apps.leads.models import ImportJob, ScoringProfile
from apps.leads.scoring_models import DEFAULT_WEIGHTS, ScoreComponent, merge_weights
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


class CountryProfileSerializer(serializers.ModelSerializer):
    """Seeded country facts (PRD section 71). Read-only: these are not a tenant's to edit."""

    id = serializers.UUIDField(source="public_id", read_only=True)

    class Meta:
        model = CountryProfile
        fields = [
            "id",
            "code",
            "name",
            "region",
            "currency",
            "languages",
            "timezones",
            "major_industries",
            "business_hubs",
            "channels",
            "communication_notes",
            "data_protection_law",
            "regulatory_notes",
            "is_launch_market",
        ]
        read_only_fields = fields


class MarketRecommendationSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    country = CountryProfileSerializer(read_only=True)
    fit_label = serializers.CharField(source="get_fit_display", read_only=True)

    class Meta:
        model = MarketRecommendation
        fields = [
            "id",
            "country",
            "fit",
            "fit_label",
            "score",
            "rank",
            "reasoning",
            "factors",
            "recommended_channels",
            "cautions",
            "is_selected",
            "prompt_pin",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class MarketRecommendRequestSerializer(serializers.Serializer):
    include_international = serializers.BooleanField(required=False, default=False)


class MarketSelectionSerializer(serializers.Serializer):
    """The markets the customer has actually decided to work."""

    codes = serializers.ListField(child=serializers.CharField(max_length=2), allow_empty=True)


class ImportJobSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    source_name = serializers.CharField(source="source.name", read_only=True)
    summary = serializers.SerializerMethodField()

    class Meta:
        model = ImportJob
        fields = [
            "id",
            "original_filename",
            "content_type",
            "size_bytes",
            "source_name",
            "status",
            "column_mapping",
            "detected_headers",
            "sample_rows",
            "summary",
            "errors",
            "error_message",
            "started_at",
            "finished_at",
            "created_at",
        ]
        read_only_fields = fields

    @extend_schema_field({"type": "object", "additionalProperties": {"type": "integer"}})
    def get_summary(self, obj: ImportJob) -> dict:
        return obj.summary()


class ImportUploadSerializer(serializers.Serializer):
    """Validates an upload before a byte of it is stored (PRD section 110)."""

    file = serializers.FileField()
    source_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    icp = serializers.UUIDField(required=False, allow_null=True)

    def validate_file(self, uploaded: Any) -> Any:
        from django.conf import settings

        if uploaded.size > settings.IMPORT_MAX_BYTES:
            limit = settings.IMPORT_MAX_BYTES // (1024 * 1024)
            raise serializers.ValidationError(f"The file is larger than {limit}MB.")

        allowed = settings.IMPORT_ALLOWED_TYPES
        extension = PurePosixPath(uploaded.name or "").suffix.lower()
        # Both the declared type and the extension must be acceptable. Either
        # alone is trivially lied about, and the parser is chosen from the
        # extension, so a mismatch is a reason to refuse rather than guess.
        if extension not in set(allowed.values()):
            raise serializers.ValidationError(
                f"Unsupported file type. Accepted: {', '.join(sorted(set(allowed.values())))}."
            )
        declared = (uploaded.content_type or "").split(";")[0].strip().lower()
        if declared and declared not in allowed:
            raise serializers.ValidationError(
                f"Unsupported content type {declared!r} for a {extension} file."
            )
        return uploaded


class ImportMappingSerializer(serializers.Serializer):
    """The confirmed column mapping, which starts the run."""

    column_mapping = serializers.DictField(child=serializers.CharField(), allow_empty=False)

    def validate_column_mapping(self, mapping: dict) -> dict:
        from apps.leads.importing import CANONICAL_FIELDS

        unknown = set(mapping) - set(CANONICAL_FIELDS)
        if unknown:
            raise serializers.ValidationError(f"Unknown field(s): {', '.join(sorted(unknown))}.")
        # Without one of these there is nothing to identify a company by, and
        # every row would create a new record.
        if not ({"company", "website", "email"} & set(mapping)):
            raise serializers.ValidationError(
                "Map at least one of company, website or email, or rows cannot be matched."
            )
        return mapping


class ProspectResearchSerializer(serializers.ModelSerializer):
    """The sales brief (PRD section 34) and the section 35 explanation.

    ``reason_sentence`` is composed on the server from the two stored halves.
    The client is given the sentence *and* the halves: the sentence to show,
    the halves because the observation is the part that carries evidence and
    the part a rep may legitimately reword.

    ``reason_rejected`` is exposed on purpose. "Nothing to say yet" and "the
    agent wrote something we could not verify and discarded it" are different
    situations, and a reader who cannot tell them apart will assume the first.
    """

    id = serializers.UUIDField(source="public_id", read_only=True)
    company = serializers.UUIDField(source="company.public_id", read_only=True)
    company_name = serializers.CharField(source="company.name", read_only=True)
    icp_name = serializers.CharField(source="icp.name", read_only=True, default=None)
    reason_sentence = serializers.CharField(read_only=True)
    has_reason = serializers.BooleanField(read_only=True)
    fields_meta = serializers.SerializerMethodField()
    source_signal_count = serializers.SerializerMethodField()

    class Meta:
        model = ProspectResearch
        fields = [
            "id",
            "company",
            "company_name",
            "icp_name",
            "summary",
            "why_they_may_buy",
            "likely_pain",
            "possible_use_case",
            "suggested_approach",
            "personalization_points",
            "decision_maker_titles",
            "reason_sentence",
            "reason_observation",
            "reason_implication",
            "reason_evidence",
            "reason_confidence",
            "reason_rejected",
            "has_reason",
            "evidence",
            "unknowns",
            "confidence",
            "status",
            "research_error",
            "prompt_pin",
            "researched_at",
            "score_at_research",
            "source_signal_count",
            "edited_fields",
            "fields_meta",
        ]
        read_only_fields = [
            "id",
            "company",
            "company_name",
            "icp_name",
            "reason_sentence",
            "reason_evidence",
            "reason_confidence",
            "reason_rejected",
            "has_reason",
            "evidence",
            "unknowns",
            "confidence",
            "status",
            "research_error",
            "prompt_pin",
            "researched_at",
            "score_at_research",
            "source_signal_count",
            "edited_fields",
            "fields_meta",
        ]

    @extend_schema_field({"type": "object"})
    def get_fields_meta(self, obj: ProspectResearch) -> dict:
        return obj.fields_meta()

    def get_source_signal_count(self, obj: ProspectResearch) -> int:
        return obj.source_signals.count()


class WebsiteAuditRequestSerializer(serializers.Serializer):
    """What a stranger submits (PRD sections 17, 49)."""

    url = serializers.CharField(max_length=2048)
    # Section 17's "optional signup". Optional means the audit runs and is
    # shown in full without it; it is not a gate.
    email = serializers.EmailField(required=False, allow_blank=True)


class WebsiteAuditSerializer(serializers.ModelSerializer):
    """An audit result.

    ``checks`` carries every measurement with what was found and how to fix
    it, and ``judged`` says whether a model saw the page at all -- because an
    audit that ran its measured half and lost the model call is still a
    useful result, and a reader is entitled to know which they have.

    The submitted email is never echoed back. It arrived from an anonymous
    form and the result is shared by link, so returning it would publish an
    address to whoever the link reaches.
    """

    id = serializers.UUIDField(source="public_id", read_only=True)
    band = serializers.CharField(read_only=True)
    failed_checks = serializers.SerializerMethodField()

    class Meta:
        model = WebsiteAudit
        fields = [
            "id",
            "url",
            "final_url",
            "domain",
            "status",
            "error_reason",
            "overall_score",
            "band",
            "scores",
            "checks",
            "failed_checks",
            "performance",
            "recommendations",
            "notes",
            "what_they_sell",
            "who_its_for",
            "confidence",
            "judged",
            "page_title",
            "page_description",
            "fetched_at",
            "created_at",
        ]
        read_only_fields = fields

    @extend_schema_field({"type": "array", "items": {"type": "object"}})
    def get_failed_checks(self, obj: WebsiteAudit) -> list[dict]:
        return obj.failed_checks


class ResearchResetSerializer(serializers.Serializer):
    fields = serializers.ListField(
        child=serializers.ChoiceField(choices=ProspectResearch.AI_FIELDS),
        allow_empty=False,
    )


class ScoringProfileSerializer(serializers.ModelSerializer):
    """The section 32 weighting, as a plain mapping.

    Weights are not required to add up to anything. A customer who sets every
    component to 10 means "weigh these equally", and the engine normalises by
    whatever they total -- so validating a sum to 100 would reject a sensible
    intent and tell them nothing useful.
    """

    id = serializers.UUIDField(source="public_id", read_only=True)
    weights = serializers.DictField(child=serializers.IntegerField(min_value=0, max_value=100))
    components = serializers.SerializerMethodField()
    is_customised = serializers.BooleanField(read_only=True)
    updated_by_email = serializers.CharField(source="updated_by.email", read_only=True)

    class Meta:
        model = ScoringProfile
        fields = [
            "id",
            "weights",
            "components",
            "is_customised",
            "notes",
            "updated_by_email",
            "updated_at",
        ]
        read_only_fields = ["id", "components", "is_customised", "updated_by_email", "updated_at"]

    @extend_schema_field({"type": "array", "items": {"type": "object"}})
    def get_components(self, obj: ScoringProfile) -> list[dict]:
        """The vocabulary, so a client can build the form without hardcoding it."""
        weights = obj.resolved_weights()
        return [
            {
                "component": value,
                "label": str(label),
                "weight": weights.get(value, 0),
                "default": DEFAULT_WEIGHTS.get(value, 0),
            }
            for value, label in ScoreComponent.choices
        ]

    def validate_weights(self, value: dict) -> dict:
        unknown = sorted(set(value) - set(ScoreComponent.values))
        if unknown:
            raise serializers.ValidationError(f"Unknown scoring components: {', '.join(unknown)}.")
        if not any(value.values()):
            raise serializers.ValidationError(
                "At least one component must carry some weight, or the score has no meaning."
            )
        # Merged rather than replaced, so omitting a component leaves it at
        # its current weight instead of silently zeroing it.
        return merge_weights(
            {**self.instance.resolved_weights(), **value} if self.instance else value
        )


class ProspectContactSerializer(serializers.ModelSerializer):
    """The one contact a prospect row shows (PRD section 117, "contact")."""

    id = serializers.UUIDField(source="public_id", read_only=True)
    name = serializers.CharField(source="display_name", read_only=True)
    contactable = serializers.BooleanField(source="can_be_emailed", read_only=True)

    class Meta:
        model = Person
        fields = ["id", "name", "job_title", "email", "email_status", "contactable"]
        read_only_fields = fields


class LeadSignalSerializer(serializers.ModelSerializer):
    """One buying signal (PRD section 33), with everything needed to judge it.

    ``evidence`` is included in full rather than counted. Section 58 makes the
    evidence the product: a rep about to mention a signal in a message needs
    to read the quote and follow the link first, and a UI that had to fetch
    each signal individually to show that would fetch none of them.

    ``strength`` and ``decayed_strength`` are both returned because they
    answer different questions -- how good this signal is, and how good it is
    *today*. Showing only the decayed figure makes a strong month-old signal
    indistinguishable from a weak new one.
    """

    id = serializers.UUIDField(source="public_id", read_only=True)
    company = serializers.UUIDField(source="company.public_id", read_only=True)
    company_name = serializers.CharField(source="company.name", read_only=True)
    company_domain = serializers.CharField(source="company.domain", read_only=True)
    decayed_strength = serializers.SerializerMethodField()
    freshness = serializers.SerializerMethodField()
    age_days = serializers.SerializerMethodField()
    is_active = serializers.SerializerMethodField()
    is_dismissed = serializers.BooleanField(read_only=True)

    class Meta:
        model = LeadSignal
        fields = [
            "id",
            "company",
            "company_name",
            "company_domain",
            "signal_type",
            "title",
            "description",
            "detector",
            "strength",
            "decayed_strength",
            "freshness",
            "confidence",
            "occurred_at",
            "detected_at",
            "last_seen_at",
            "expires_at",
            "age_days",
            "is_active",
            "is_dismissed",
            "dismiss_reason",
            "source",
            "source_url",
            "evidence",
        ]
        read_only_fields = fields

    def get_decayed_strength(self, obj: LeadSignal) -> int:
        return obj.decayed_strength()

    def get_freshness(self, obj: LeadSignal) -> float:
        return obj.freshness()

    def get_age_days(self, obj: LeadSignal) -> int:
        return obj.age_days()

    def get_is_active(self, obj: LeadSignal) -> bool:
        return obj.is_active()


class SignalDismissSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True)


class ProspectSignalSerializer(serializers.ModelSerializer):
    """The compact form shown on a prospect row (PRD section 117)."""

    id = serializers.UUIDField(source="public_id", read_only=True)
    decayed_strength = serializers.SerializerMethodField()
    evidence_count = serializers.SerializerMethodField()

    class Meta:
        model = LeadSignal
        fields = [
            "id",
            "signal_type",
            "title",
            "occurred_at",
            "detected_at",
            "expires_at",
            "strength",
            "decayed_strength",
            "confidence",
            "source",
            "source_url",
            "evidence_count",
        ]
        read_only_fields = fields

    def get_decayed_strength(self, obj: LeadSignal) -> int:
        return obj.decayed_strength()

    def get_evidence_count(self, obj: LeadSignal) -> int:
        return len(obj.evidence or [])


class CompanyEventSerializer(serializers.ModelSerializer):
    """A recorded fact about a company, as distinct from a signal.

    Kept available because the two are not interchangeable: an event is dated
    history that never expires, a signal is a reason to call that does.
    """

    id = serializers.UUIDField(source="public_id", read_only=True)

    class Meta:
        model = CompanyEvent
        fields = ["id", "event_type", "title", "occurred_at", "url", "source", "confidence"]
        read_only_fields = fields


class ProspectSerializer(serializers.ModelSerializer):
    """One row of the prospect table (PRD section 117).

    The columns the PRD names are assembled here rather than left to the
    client: `score`, `status`, `owner` and `last activity` live on the Lead,
    `signals` on the company's events, and a table that had to stitch those
    together itself would make N+1 queries to draw one page.
    """

    id = serializers.UUIDField(source="public_id", read_only=True)
    contact = serializers.SerializerMethodField()
    signals = serializers.SerializerMethodField()
    lead = serializers.SerializerMethodField()
    reason = serializers.SerializerMethodField()
    is_stale = serializers.BooleanField(read_only=True)

    class Meta:
        model = Company
        fields = [
            "id",
            "name",
            "domain",
            "website",
            "country",
            "city",
            "industry",
            "employee_range",
            "description",
            "status",
            "source",
            "last_verified_at",
            "is_stale",
            "contact",
            "signals",
            "lead",
            "reason",
        ]
        read_only_fields = fields

    @extend_schema_field(ProspectContactSerializer(allow_null=True))
    def get_contact(self, obj: Company) -> dict | None:
        # `prefetched_people` is set by the view; falling back to a query here
        # would reintroduce the N+1 the prefetch exists to avoid.
        people = getattr(obj, "prefetched_people", None)
        if people is None:
            return None
        best = next((person for person in people if person.can_be_emailed), None)
        chosen = best or (people[0] if people else None)
        return ProspectContactSerializer(chosen).data if chosen else None

    @extend_schema_field(ProspectSignalSerializer(many=True))
    def get_signals(self, obj: Company) -> list:
        # `active_signals` is set by the view's prefetch and holds live
        # signals only. An expired one is not a reason to call, and putting it
        # on the row would undo the expiry that makes signals trustworthy.
        return ProspectSignalSerializer(getattr(obj, "active_signals", []), many=True).data

    @extend_schema_field(
        {
            "type": "object",
            "nullable": True,
            "properties": {
                "id": {"type": "string"},
                "status": {"type": "string"},
                "score": {"type": "integer"},
                "band": {"type": "string"},
                "confidence": {"type": "integer"},
                "scored_at": {"type": "string", "nullable": True},
                "owner": {"type": "string", "nullable": True},
                "last_activity_at": {"type": "string", "nullable": True},
            },
        }
    )
    @extend_schema_field(
        {
            "type": "object",
            "nullable": True,
            "properties": {
                "sentence": {"type": "string"},
                "confidence": {"type": "string"},
                "evidence_count": {"type": "integer"},
                "rejected": {"type": "string"},
            },
        }
    )
    def get_reason(self, obj: Company) -> dict | None:
        """The section 35 explanation, where one has been verified."""
        research = getattr(obj, "prefetched_research", None)
        if not research:
            return None
        brief = research[0]
        if not brief.has_reason:
            # Still returned, carrying why. A row that silently shows nothing
            # looks identical whether the agent has not run, found nothing
            # worth saying, or wrote something that failed verification.
            return {
                "sentence": "",
                "confidence": "",
                "evidence_count": 0,
                "rejected": brief.reason_rejected,
            }
        return {
            "sentence": brief.reason_sentence,
            "confidence": brief.reason_confidence,
            "evidence_count": len(brief.reason_evidence or []),
            "rejected": "",
        }

    def get_lead(self, obj: Company) -> dict | None:
        leads = getattr(obj, "prefetched_leads", None)
        if not leads:
            return None
        lead = leads[0]
        breakdown = lead.score_breakdown or {}
        return {
            "id": str(lead.public_id),
            "status": lead.status,
            "score": lead.score,
            # The band and confidence come from the stored breakdown rather
            # than being recomputed here: the server names the band so the
            # label and the badge colour cannot disagree, and a score of 82
            # from three components is a different claim from 82 from eight.
            "band": breakdown.get("band", ""),
            "confidence": breakdown.get("confidence"),
            "scored_at": lead.scored_at,
            "owner": lead.owner.get_full_name() if lead.owner else None,
            "last_activity_at": lead.last_activity_at,
        }


class SavedSearchSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    created_by_email = serializers.CharField(source="created_by.email", read_only=True)

    class Meta:
        model = SavedSearch
        fields = [
            "id",
            "name",
            "description",
            "filters",
            "is_shared",
            "created_by_email",
            "last_run_at",
            "last_result_count",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "created_by_email",
            "last_run_at",
            "last_result_count",
            "created_at",
        ]
