import pytest

from apps.accounts.models import User
from apps.audit.models import AuditLog

pytestmark = pytest.mark.django_db

URL = "/api/v1/users/"


def test_owner_creates_user_with_branches(
    owner_client, owner, roles, branch, branch2, django_capture_on_commit_callbacks
):
    payload = {
        "username": "yangi",
        "password": "parol12345",
        "full_name": "Yangi Sotuvchi",
        "phone": "+998901234567",
        "role": roles["seller"].id,
        "branch_ids": [branch2.id, branch.id],
        "default_branch_id": branch.id,
    }
    with django_capture_on_commit_callbacks(execute=True):
        response = owner_client.post(URL, payload)
    assert response.status_code == 201, response.json()
    body = response.json()
    assert body["username"] == "yangi"
    assert body["role_detail"] == {"code": "seller", "name": "Sotuvchi"}
    assert {b["id"] for b in body["branches"]} == {branch.id, branch2.id}
    assert next(b for b in body["branches"] if b["id"] == branch.id)["is_default"] is True
    assert "password" not in body

    user = User.objects.get(username="yangi")
    assert user.check_password("parol12345")
    assert user.accessible_branch_ids() == {branch.id, branch2.id}

    log = AuditLog.objects.get(event_name="user.created")
    assert log.actor == owner
    assert log.aggregate_id == user.id
    assert log.payload["branch_ids"] == sorted([branch.id, branch2.id])
    assert "password" not in log.payload


def test_seller_cannot_manage_users(seller_client, roles):
    assert seller_client.get(URL).status_code == 403
    response = seller_client.post(URL, {"username": "x"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"


def test_validation_errors(owner_client, roles):
    response = owner_client.post(
        URL, {"username": "x", "password": "123", "role": roles["seller"].id}
    )
    assert response.status_code == 400
    details = {d["field"]: d["code"] for d in response.json()["error"]["details"]}
    assert details["full_name"] == "required"
    assert details["password"] == "password_too_weak"


def test_duplicate_username(owner_client, roles, seller):
    response = owner_client.post(
        URL,
        {
            "username": "SOTUVCHI",
            "password": "parol12345",
            "full_name": "X",
            "role": roles["seller"].id,
        },
    )
    assert response.status_code == 400
    assert response.json()["error"]["details"] == [
        {"field": "username", "code": "unique", "message": "Bu login band"}
    ]


def test_default_branch_must_be_among_branches(owner_client, roles, branch, branch2):
    response = owner_client.post(
        URL,
        {
            "username": "u",
            "password": "parol12345",
            "full_name": "U",
            "role": roles["seller"].id,
            "branch_ids": [branch.id],
            "default_branch_id": branch2.id,
        },
    )
    assert response.status_code == 400
    assert response.json()["error"]["details"][0]["field"] == "default_branch_id"


def test_deactivate_user_emits_events(owner_client, seller, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        response = owner_client.patch(f"{URL}{seller.id}/", {"is_active": False})
    assert response.status_code == 200
    assert response.json()["is_active"] is False
    updated = AuditLog.objects.get(event_name="user.updated")
    assert updated.payload["changes"] == {"is_active": {"old": True, "new": False}}
    assert AuditLog.objects.filter(event_name="user.deactivated", aggregate_id=seller.id).exists()


def test_update_branches_and_role(
    owner_client, seller, roles, branch, branch2, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        response = owner_client.patch(
            f"{URL}{seller.id}/",
            {
                "role": roles["storekeeper"].id,
                "branch_ids": [branch2.id],
                "default_branch_id": branch2.id,
            },
        )
    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["role_detail"]["code"] == "storekeeper"
    assert [b["id"] for b in body["branches"]] == [branch2.id]
    changes = AuditLog.objects.get(event_name="user.updated").payload["changes"]
    assert changes["role_id"] == {"old": roles["seller"].id, "new": roles["storekeeper"].id}
    assert changes["branch_ids"] == {"old": [branch.id], "new": [branch2.id]}


def test_noop_update_emits_nothing(owner_client, seller, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        response = owner_client.patch(f"{URL}{seller.id}/", {"full_name": seller.full_name})
    assert response.status_code == 200
    assert not AuditLog.objects.filter(event_name="user.updated").exists()


def test_set_password(owner_client, seller, api_client, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        response = owner_client.post(
            f"{URL}{seller.id}/set-password/", {"new_password": "boshqaParol7"}
        )
    assert response.status_code == 204
    login = api_client.post(
        "/api/v1/auth/login/", {"username": "sotuvchi", "password": "boshqaParol7"}
    )
    assert login.status_code == 200
    assert AuditLog.objects.get(event_name="user.password_changed").payload["by_self"] is False


def test_list_filter_search_and_pagination(owner_client, owner, seller, storekeeper, roles):
    response = owner_client.get(URL)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"count", "page", "page_size", "total_pages", "results"}
    assert body["count"] == 3
    assert body["page"] == 1 and body["page_size"] == 25 and body["total_pages"] == 1

    assert owner_client.get(URL, {"role": roles["seller"].id}).json()["count"] == 1
    assert owner_client.get(URL, {"search": "ombor"}).json()["results"][0]["username"] == "omborchi"
    page = owner_client.get(URL, {"page_size": 2, "page": 2}).json()
    assert page["page"] == 2 and page["total_pages"] == 2 and len(page["results"]) == 1


def test_no_delete_endpoint(owner_client, seller):
    assert owner_client.delete(f"{URL}{seller.id}/").status_code == 405
