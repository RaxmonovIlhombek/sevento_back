import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter  # noqa: E402

# WebSocket marshruti 2-bosqichda (apps.realtime) qo'shiladi.
application = ProtocolTypeRouter({"http": django_asgi_app})
