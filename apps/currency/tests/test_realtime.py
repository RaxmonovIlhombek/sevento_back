"""currency.rate_updated hodisasi broadcast guruhiga yetib kelishi (WebSocket)."""

from decimal import Decimal

import pytest
from channels.db import database_sync_to_async

from apps.currency import services
from apps.currency.models import Currency
from apps.realtime import tickets
from config.asgi import application

pytestmark = pytest.mark.django_db(transaction=True)


async def test_rate_update_reaches_all_connected(seller, owner):
    from channels.testing.websocket import WebsocketCommunicator

    communicator = WebsocketCommunicator(
        application, "/ws/v1/", headers=[(b"origin", b"http://testserver")]
    )
    assert (await communicator.connect())[0]
    ticket = tickets.issue_ticket(seller)[0]
    await communicator.send_json_to({"type": "auth", "payload": {"ticket": ticket}})
    assert (await communicator.receive_json_from())["type"] == "auth.ok"

    def set_rate():
        # transaction=True testlari MB ni tozalaydi (seed migratsiya ma'lumoti ham) — shuning uchun
        usd, _ = Currency.objects.get_or_create(code="USD", defaults={"name": "AQSH dollari"})
        services.set_rate(actor=owner, currency=usd, rate=Decimal("12700"))

    await database_sync_to_async(set_rate)()
    message = await communicator.receive_json_from()
    assert message["type"] == "currency.rate_updated"
    assert message["payload"]["source"] == "manual"
    assert message["payload"]["rates"][0]["currency"] == "USD"
    assert message["payload"]["rates"][0]["rate"] == "12700.000000"
    await communicator.disconnect()
