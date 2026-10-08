from django.contrib import admin

from apps.ai.models import AIJob
from apps.common.admin import ReadOnlyModelAdmin


@admin.register(AIJob)
class AIJobAdmin(ReadOnlyModelAdmin):
    """Job history is an audit trail; editing it would defeat the purpose."""

    list_display = (
        "created_at",
        "feature",
        "model_id",
        "status",
        "cost_micro_usd",
        "organization",
    )
    list_filter = ("status", "feature", "model_id", "tier")
    search_fields = ("feature", "prompt_name", "subject_id", "organization__name")
    date_hierarchy = "created_at"
