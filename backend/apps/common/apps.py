from django.apps import AppConfig
from django.conf import settings


class CommonConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.common"
    verbose_name = "Common"

    def ready(self) -> None:
        # Development convenience, installed from one place so that every CSRF
        # path honours it -- the middleware and DRF's own checker alike. The
        # dev settings module is the only thing that turns it on.
        if settings.DEBUG and getattr(settings, "TRUST_PRIVATE_NETWORK_CSRF", False):
            from apps.common.dev_middleware import install_private_network_trust

            install_private_network_trust()
