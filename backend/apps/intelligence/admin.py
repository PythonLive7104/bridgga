from django.contrib import admin

from apps.common.admin import ReadOnlyModelAdmin
from apps.intelligence.models import WebsiteSnapshot


@admin.register(WebsiteSnapshot)
class WebsiteSnapshotAdmin(ReadOnlyModelAdmin):
    """Snapshots are evidence; editing one would undermine its provenance."""

    list_display = ("requested_url", "organization", "status", "status_code", "fetched_at")
    list_filter = ("status",)
    search_fields = ("requested_url", "final_url", "title", "organization__name")
    date_hierarchy = "created_at"
