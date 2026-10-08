from django.contrib import admin

from apps.common.admin import UnscopedModelAdmin
from apps.organizations.models import Invitation, Membership, Organization, Workspace


class MembershipInline(admin.TabularInline):
    model = Membership
    extra = 0
    autocomplete_fields = ("user",)
    readonly_fields = ("public_id", "joined_at")


@admin.register(Organization)
class OrganizationAdmin(UnscopedModelAdmin):
    list_display = ("name", "slug", "country", "default_currency", "is_active", "created_at")
    list_filter = ("is_active", "country", "default_currency")
    search_fields = ("name", "slug", "website")
    readonly_fields = ("public_id", "created_at", "updated_at")
    inlines = (MembershipInline,)


@admin.register(Workspace)
class WorkspaceAdmin(UnscopedModelAdmin):
    list_display = ("name", "organization", "is_default", "country", "created_at")
    list_filter = ("is_default", "country")
    search_fields = ("name", "organization__name")
    readonly_fields = ("public_id", "created_at", "updated_at")


@admin.register(Membership)
class MembershipAdmin(UnscopedModelAdmin):
    list_display = ("user", "organization", "role", "is_active", "joined_at")
    list_filter = ("role", "is_active")
    search_fields = ("user__email", "organization__name")
    readonly_fields = ("public_id", "created_at", "updated_at")


@admin.register(Invitation)
class InvitationAdmin(UnscopedModelAdmin):
    list_display = ("email", "organization", "role", "expires_at", "accepted_at", "revoked_at")
    list_filter = ("role",)
    search_fields = ("email", "organization__name")
    # token_hash stays hidden: the admin has no reason to see it.
    exclude = ("token_hash",)
    readonly_fields = ("public_id", "created_at", "updated_at")
