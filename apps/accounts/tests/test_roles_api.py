import pytest

from apps.accounts.models import Role
from apps.audit.models import AuditLog

pytestmark = pytest.mark.django_db

URL = "/api/v1/roles/"


def test_list_roles_with_users_count(owner_client, owner, seller, storekeeper):
    response = owner_client.get(URL)
    assert response.status_code == 200
    by_code = {r["code"]: r for r in response.json()["results"]}
    assert set(by_code) >= {"owner", "accountant", "storekeeper", "seller"}
    assert by_code["seller"]["users_count"] == 1
    assert by_code["accountant"]["users_count"] == 0
    assert by_code["owner"]["is_system"] is True


def test_seller_cannot_see_roles(seller_client):
    assert seller_client.get(URL).status_code == 403


def test_create_role(owner_client, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        response = owner_client.post(
            URL,
            {
                "code": "cashier",
                "name": "Kassir",
                "capabilities": ["payments.receive", "cashbox.view", "payments.receive"],
            },
        )
    assert response.status_code == 201, response.json()
    assert response.json()["capabilities"] == ["cashbox.view", "payments.receive"]
    assert response.json()["is_system"] is False
    assert AuditLog.objects.get(event_name="role.created").payload["code"] == "cashier"


def test_duplicate_code_rejected(owner_client, roles):
    response = owner_client.post(URL, {"code": "seller", "name": "X", "capabilities": []})
    assert response.status_code == 400
    assert response.json()["error"]["details"] == [
        {"field": "code", "code": "unique", "message": "Bu kod band"}
    ]


def test_unknown_capability_rejected(owner_client):
    response = owner_client.post(URL, {"code": "x", "name": "X", "capabilities": ["sales.fly"]})
    assert response.status_code == 400
    detail = response.json()["error"]["details"][0]
    assert detail["field"] == "capabilities" and detail["code"] == "unknown_capability"


def test_update_role_capabilities(owner_client, roles, django_capture_on_commit_callbacks):
    role = roles["seller"]
    with django_capture_on_commit_callbacks(execute=True):
        response = owner_client.patch(f"{URL}{role.id}/", {"capabilities": ["sales.view"]})
    assert response.status_code == 200
    role.refresh_from_db()
    assert role.capabilities == ["sales.view"]
    changes = AuditLog.objects.get(event_name="role.updated").payload["changes"]
    assert changes["capabilities"]["new"] == ["sales.view"]


def test_system_role_code_locked(owner_client, roles):
    response = owner_client.patch(f"{URL}{roles['seller'].id}/", {"code": "sotuvchi"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "system_role"


def test_delete_rules(owner_client, roles, seller, django_capture_on_commit_callbacks):
    assert (
        owner_client.delete(f"{URL}{roles['owner'].id}/").json()["error"]["code"] == "system_role"
    )

    custom = Role.objects.create(code="temp", name="Temp", capabilities=[])
    seller.role = custom
    seller.save()
    response = owner_client.delete(f"{URL}{custom.id}/")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "role_in_use"

    seller.role = roles["seller"]
    seller.save()
    with django_capture_on_commit_callbacks(execute=True):
        assert owner_client.delete(f"{URL}{custom.id}/").status_code == 204
    assert not Role.objects.filter(code="temp").exists()
    assert AuditLog.objects.filter(event_name="role.deleted").exists()
