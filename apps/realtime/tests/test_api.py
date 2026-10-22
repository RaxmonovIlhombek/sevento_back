import pytest
from django.core.cache import cache

from apps.audit.models import AuditLog
from apps.realtime import connections, tickets

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


def test_ticket_endpoint(seller_client, api_client, seller):
    response = seller_client.post("/api/v1/realtime/ticket/")
    assert response.status_code == 201
    body = response.json()
    assert body["expires_in"] == 30
    assert len(body["ticket"]) >= 32
    assert tickets.consume_ticket(body["ticket"]) == seller.id
    assert tickets.consume_ticket(body["ticket"]) is None  # bir martalik

    assert api_client.post("/api/v1/realtime/ticket/").status_code == 401


def test_consume_unknown_ticket():
    assert tickets.consume_ticket("") is None
    assert tickets.consume_ticket("x" * 200) is None
    assert tickets.consume_ticket("nope") is None


def test_notice_requires_settings_manage(
    seller_client, owner_client, django_capture_on_commit_callbacks
):
    assert seller_client.post("/api/v1/realtime/notice/", {"message": "x"}).status_code == 403
    response = owner_client.post("/api/v1/realtime/notice/", {"message": ""})
    assert response.status_code == 400
    with django_capture_on_commit_callbacks(execute=True):
        response = owner_client.post(
            "/api/v1/realtime/notice/", {"message": "Diqqat", "level": "info"}
        )
    assert response.status_code == 204
    log = AuditLog.objects.get(event_name="system.notice")
    assert log.payload == {"level": "info", "message": "Diqqat"}


def test_connection_counter():
    assert connections.count(7) == 0
    assert connections.register(7) == 1
    assert connections.register(7) == 2
    connections.release(7)
    assert connections.count(7) == 1
    connections.release(7)
    connections.release(7)  # ortiqcha release zarar qilmaydi
    assert connections.count(7) == 0
