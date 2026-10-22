"""WebSocket: autentifikatsiya (ticket), ruxsat (guruhlar), xabar yetkazish, yopish kodlari."""

import pytest
from channels.db import database_sync_to_async
from django.db import transaction

from apps.accounts import events as account_events
from apps.realtime import router, tickets
from apps.realtime.envelope import envelope
from config.asgi import application

pytestmark = pytest.mark.django_db(transaction=True)

ORIGIN = [(b"origin", b"http://testserver")]


async def connect(ticket=None):
    from channels.testing.websocket import WebsocketCommunicator  # daphne siz

    communicator = WebsocketCommunicator(application, "/ws/v1/", headers=ORIGIN)
    connected, _ = await communicator.connect()
    assert connected
    if ticket is not None:
        await communicator.send_json_to({"type": "auth", "payload": {"ticket": ticket}})
    return communicator


async def expect_close(communicator, code: int):
    message = await communicator.receive_output(timeout=2)
    assert message["type"] == "websocket.close", message
    assert message["code"] == code


def ticket_for(user) -> str:
    return tickets.issue_ticket(user)[0]


async def test_auth_ok_joins_groups(seller, branch):
    communicator = await connect(ticket_for(seller))
    message = await communicator.receive_json_from()
    assert message["type"] == "auth.ok"
    assert message["payload"] == {
        "user_id": seller.id,
        "groups": [f"user_{seller.id}", "role_seller", f"branch_{branch.id}", "broadcast"],
    }
    assert message["timestamp"]
    await communicator.disconnect()


async def test_no_auth_within_timeout(settings):
    communicator = await connect()
    await expect_close(communicator, 4408)


async def test_non_auth_message_before_auth(db):
    communicator = await connect()
    await communicator.send_json_to({"type": "ping"})
    await expect_close(communicator, 4401)


async def test_invalid_ticket(db):
    communicator = await connect("yaroqsiz")
    message = await communicator.receive_json_from()
    assert message["type"] == "auth.error"
    assert message["payload"]["code"] == "invalid_ticket"
    await expect_close(communicator, 4401)


async def test_ticket_is_single_use(seller):
    ticket = ticket_for(seller)
    first = await connect(ticket)
    assert (await first.receive_json_from())["type"] == "auth.ok"
    second = await connect(ticket)
    assert (await second.receive_json_from())["type"] == "auth.error"
    await expect_close(second, 4401)
    await first.disconnect()


async def test_inactive_user_rejected(seller):
    await database_sync_to_async(
        lambda: type(seller).objects.filter(pk=seller.pk).update(is_active=False)
    )()
    communicator = await connect(ticket_for(seller))
    await expect_close(communicator, 4403)


async def test_ping_pong(seller):
    communicator = await connect(ticket_for(seller))
    await communicator.receive_json_from()
    await communicator.send_json_to({"type": "ping"})
    assert (await communicator.receive_json_from())["type"] == "pong"
    await communicator.send_to(text_data="bu json emas")  # e'tiborsiz
    await communicator.send_json_to({"type": "ping"})
    assert (await communicator.receive_json_from())["type"] == "pong"
    await communicator.disconnect()


async def test_group_isolation(seller, owner, branch, branch2):
    """Sotuvchi faqat o'z nuqtasi guruhini oladi; rahbar hammasini."""
    seller_ws = await connect(ticket_for(seller))
    owner_ws = await connect(ticket_for(owner))
    await seller_ws.receive_json_from()
    await owner_ws.receive_json_from()

    message = envelope("stock.changed", {"branch_id": branch2.id, "product_id": 1})
    await database_sync_to_async(router.send_to_groups)([f"branch_{branch2.id}"], message)

    received = await owner_ws.receive_json_from()
    assert received["type"] == "stock.changed"
    assert received["payload"]["branch_id"] == branch2.id
    assert await seller_ws.receive_nothing(timeout=0.3)

    await database_sync_to_async(router.send_to_groups)([f"branch_{branch.id}"], message)
    assert (await seller_ws.receive_json_from())["type"] == "stock.changed"
    assert (await owner_ws.receive_json_from())["type"] == "stock.changed"

    await seller_ws.disconnect()
    await owner_ws.disconnect()


async def test_event_after_commit_reaches_socket_and_revokes(seller, owner):
    """user.deactivated (commit dan keyin) → session.revoked + 4403; boshqalarga ta'sir yo'q."""
    seller_ws = await connect(ticket_for(seller))
    owner_ws = await connect(ticket_for(owner))
    await seller_ws.receive_json_from()
    await owner_ws.receive_json_from()

    def deactivate():
        with transaction.atomic():
            account_events.UserDeactivated.publish_from(
                actor=owner, user_id=seller.id, username=seller.username
            )

    await database_sync_to_async(deactivate)()

    message = await seller_ws.receive_json_from()
    assert message["type"] == "session.revoked"
    assert message["payload"] == {"reason": "deactivated"}
    await expect_close(seller_ws, 4403)
    assert await owner_ws.receive_nothing(timeout=0.3)
    await owner_ws.disconnect()


async def test_rolled_back_event_sends_nothing(seller, owner):
    seller_ws = await connect(ticket_for(seller))
    await seller_ws.receive_json_from()

    def deactivate_then_fail():
        with pytest.raises(RuntimeError):
            with transaction.atomic():
                account_events.UserDeactivated.publish_from(
                    actor=owner, user_id=seller.id, username=seller.username
                )
                raise RuntimeError("rollback")

    await database_sync_to_async(deactivate_then_fail)()
    assert await seller_ws.receive_nothing(timeout=0.3)
    await seller_ws.disconnect()


async def test_role_capability_change_revokes_role_group(seller, owner, roles):
    seller_ws = await connect(ticket_for(seller))
    await seller_ws.receive_json_from()

    def change_role():
        with transaction.atomic():
            account_events.RoleUpdated.publish_from(
                actor=owner,
                role_id=roles["seller"].id,
                code="seller",
                changes={"capabilities": {"old": [], "new": ["sales.view"]}},
            )

    await database_sync_to_async(change_role)()
    message = await seller_ws.receive_json_from()
    assert message["type"] == "session.revoked"
    assert message["payload"]["reason"] == "permissions_changed"
    await expect_close(seller_ws, 4403)


async def test_user_updated_without_access_change_is_silent(seller, owner):
    seller_ws = await connect(ticket_for(seller))
    await seller_ws.receive_json_from()

    def rename():
        with transaction.atomic():
            account_events.UserUpdated.publish_from(
                actor=owner,
                user_id=seller.id,
                username=seller.username,
                changes={"full_name": {"old": "A", "new": "B"}},
            )

    await database_sync_to_async(rename)()
    assert await seller_ws.receive_nothing(timeout=0.3)
    await seller_ws.disconnect()


async def test_connection_limit(seller, settings):
    settings.REALTIME = {**settings.REALTIME, "MAX_CONNECTIONS_PER_USER": 2}
    first = await connect(ticket_for(seller))
    second = await connect(ticket_for(seller))
    await first.receive_json_from()
    await second.receive_json_from()
    third = await connect(ticket_for(seller))
    await expect_close(third, 4429)
    await first.disconnect()
    await second.disconnect()
    # ulanishlar yopilgach hisob kamayadi — yana ulanish mumkin
    fourth = await connect(ticket_for(seller))
    assert (await fourth.receive_json_from())["type"] == "auth.ok"
    await fourth.disconnect()


async def test_notice_broadcast_via_api(owner, seller, as_user):
    seller_ws = await connect(ticket_for(seller))
    await seller_ws.receive_json_from()

    def post_notice():
        client = as_user(owner)
        return client.post("/api/v1/realtime/notice/", {"level": "warning", "message": "Salom"})

    response = await database_sync_to_async(post_notice)()
    assert response.status_code == 204
    message = await seller_ws.receive_json_from()
    assert message["type"] == "system.notice"
    assert message["payload"] == {"level": "warning", "message": "Salom"}
    await seller_ws.disconnect()
