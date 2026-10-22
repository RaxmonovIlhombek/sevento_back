from django.urls import path

from .consumers import RealtimeConsumer

websocket_urlpatterns = [
    path("ws/v1/", RealtimeConsumer.as_asgi()),
]
