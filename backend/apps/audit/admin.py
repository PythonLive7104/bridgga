from django.contrib import admin

from apps.audit.models import AuditLog
from apps.common.admin import ReadOnlyModelAdmin


@admin.register(AuditLog)
class AuditLogAdmin(ReadOnlyModelAdmin):
    list_display = ("created_at", "action", "actor_email", "organization", "target_label")
    list_filter = ("action",)
    search_fields = ("actor_email", "target_label", "request_id")
    date_hierarchy = "created_at"
