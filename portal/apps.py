from django.apps import AppConfig


class PortalConfig(AppConfig):
    name = 'portal'

    def ready(self):
        # Connect the Anymail delivery-tracking receiver (Tier B delivery).
        from . import webhook_handlers  # noqa: F401
