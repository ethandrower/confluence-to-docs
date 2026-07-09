"""ASGI entrypoint. HTTP goes through Django (WhiteNoise, SPA, REST); the
websocket protocol is handled by Channels. WS routes are added in Task 3."""
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'citemed.settings')

# Must build the Django ASGI app before importing anything that touches models.
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402

application = ProtocolTypeRouter({
    'http': django_asgi_app,
    'websocket': AllowedHostsOriginValidator(URLRouter([])),  # routes added in Task 3
})
