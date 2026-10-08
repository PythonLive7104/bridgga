from django.apps import AppConfig


class AiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.ai"
    verbose_name = "AI"

    def ready(self) -> None:
        # Import for the side effect of registering prompts, so get_prompt()
        # works regardless of which module is imported first.
        from apps.ai import prompts  # noqa: F401
