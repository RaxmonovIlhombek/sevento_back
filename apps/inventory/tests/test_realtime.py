"""stock.changed faqat o'sha nuqta guruhiga boradi (sotuvchi begona nuqta xabarini olmaydi)."""

from decimal import Decimal

import pytest
from channels.db import database_sync_to_async
from django.db import transaction

from apps.catalog.models import Product, Unit
from apps.inventory import services
from apps.inventory.types import DocRef, MovementType
from apps.realtime import tickets
from config.asgi import application

pytestmark = pytest.mark.django_db(transaction=True)


async def _connect(user):
    from channels.testing.websocket import WebsocketCommunicator

    communicator = WebsocketCommunicator(
        application, "/ws/v1/", headers=[(b"origin", b"http://testserver")]
    )
    assert (await communicator.connect())[0]
    await communicator.send_json_to(
        {"type": "auth", "payload": {"ticket": tickets.issue_ticket(user)[0]}}
    )
    assert (await communicator.receive_json_from())["type"] == "auth.ok"
    return communicator


async def test_stock_changed_goes_to_branch_group_only(seller, owner, branch, branch2):
    seller_ws = await _connect(seller)  # faqat branch

    def receive(target_branch):
        # transaction=True testlari seed ni o'chiradi — birlikni yaratamiz
        unit, _ = Unit.objects.get_or_create(code="dona", defaults={"name": "Dona"})
        product, _ = Product.objects.get_or_create(
            sku="RT1", defaults={"name": "Suv", "unit": unit}
        )
        with transaction.atomic():
            services.receive_stock(
                actor=owner,
                branch_id=target_branch.id,
                product_id=product.id,
                quantity=Decimal("3"),
                unit_cost_base=Decimal("1"),
                movement_type=MovementType.PURCHASE_IN,
                doc=DocRef(type="purchase", id=1, number="K-1"),
            )
        return product.id

    await database_sync_to_async(receive)(branch2)
    assert await seller_ws.receive_nothing(timeout=0.3)  # begona nuqta

    product_id = await database_sync_to_async(receive)(branch)
    message = await seller_ws.receive_json_from()
    assert message["type"] == "stock.changed"
    assert message["payload"]["branch_id"] == branch.id
    assert message["payload"]["product_id"] == product_id
    assert message["payload"]["quantity"] == "3.000"
    assert message["payload"]["document"] == {"type": "purchase", "id": 1, "number": "K-1"}
    assert "unit_cost_base" not in message["payload"]
    await seller_ws.disconnect()
