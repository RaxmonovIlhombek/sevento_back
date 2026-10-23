"""Desktop (Tauri) WebView Origin lari WebSocket da sukut bo'yicha ruxsat etilgan, begonalari yo'q.

Test sozlamalarida ALLOWED_ORIGINS = ["*"], shuning uchun bu yerda base dagi default ro'yxat
(DJANGO_TRUSTED_ORIGINS + Tauri) bilan OriginValidator alohida tekshiriladi.
"""

import pytest
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.security.websocket import OriginValidator
from channels.testing import WebsocketCommunicator

from config.settings import base

# Channels consumer chaqiruvida eski DB ulanishlarini yopadi — DB ruxsati kerak
pytestmark = pytest.mark.django_db(transaction=True)


class _Accept(AsyncWebsocketConsumer):
    async def connect(self):
        await self.accept()


async def _connects(origin: bytes) -> bool:
    app = OriginValidator(_Accept.as_asgi(), base.REALTIME["ALLOWED_ORIGINS"])
    communicator = WebsocketCommunicator(app, "/ws/v1/", headers=[(b"origin", origin)])
    connected, _ = await communicator.connect()
    await communicator.disconnect()
    return connected


def test_default_list_contains_tauri_origins():
    allowed = base.REALTIME["ALLOWED_ORIGINS"]
    assert "tauri://localhost" in allowed  # macOS, Linux
    assert "http://tauri.localhost" in allowed  # Windows (WebView2)


@pytest.mark.asyncio
@pytest.mark.parametrize("origin", [b"tauri://localhost", b"http://tauri.localhost"])
async def test_tauri_webview_origin_accepted(origin):
    assert await _connects(origin)


@pytest.mark.asyncio
@pytest.mark.parametrize("origin", [b"https://evil.example", b"tauri://evil", b"null"])
async def test_foreign_origin_rejected(origin):
    assert not await _connects(origin)
