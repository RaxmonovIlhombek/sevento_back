import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import OriginValidator  # noqa: E402

from apps.realtime import conf as realtime_conf  # noqa: E402
from apps.realtime.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        # Autentifikatsiya ticket orqali consumer ichida; bu yerda faqat Origin tekshiruvi
        "websocket": OriginValidator(
            URLRouter(websocket_urlpatterns), realtime_conf.get("ALLOWED_ORIGINS")
        ),
    }
)
