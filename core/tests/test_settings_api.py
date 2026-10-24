"""Tizim sozlamalari API: ro'yxat, o'qish, o'zgartirish (tur tekshiruvi), default ga qaytarish."""

import pytest

from core import settings_service
from core.models import OutboxEvent

pytestmark = pytest.mark.django_db

URL = "/api/v1/settings/"
KEY = "reports.keep_days"


def test_list_and_detail_with_defaults(owner_client):
    response = owner_client.get(URL)
    assert response.status_code == 200
    item = next(i for i in response.json() if i["key"] == KEY)
    assert (item["type"], item["default"], item["value"]) == ("int", 7, 7)
    detail = owner_client.get(f"{URL}{KEY}/")
    assert detail.status_code == 200 and detail.json()["value"] == 7


def test_update_validates_type_and_audits(owner_client, django_capture_on_commit_callbacks):
    bad = owner_client.put(f"{URL}{KEY}/", {"value": "ko'p"}, format="json")
    assert bad.status_code == 400
    assert bad.json()["error"]["details"][0]["field"] == "value"

    with django_capture_on_commit_callbacks(execute=True):
        ok = owner_client.put(f"{URL}{KEY}/", {"value": 14}, format="json")
    assert ok.status_code == 200 and ok.json()["value"] == 14
    assert settings_service.get(KEY) == 14
    event = OutboxEvent.objects.filter(name="setting.changed").latest("id")
    assert (event.payload["old_value"], event.payload["new_value"]) == (7, 14)


def test_delete_resets_to_default(owner_client):
    owner_client.put(f"{URL}{KEY}/", {"value": 30}, format="json")
    response = owner_client.delete(f"{URL}{KEY}/")
    assert response.status_code == 200 and response.json()["value"] == 7
    assert settings_service.get(KEY) == 7


def test_unknown_key_404_and_permissions(owner_client, seller_client):
    for method in ("get", "put", "delete"):
        response = getattr(owner_client, method)(f"{URL}yoq.sozlama/", {"value": 1}, format="json")
        assert response.status_code == 404, method
    assert seller_client.get(URL).status_code == 403
    assert seller_client.put(f"{URL}{KEY}/", {"value": 1}, format="json").status_code == 403
