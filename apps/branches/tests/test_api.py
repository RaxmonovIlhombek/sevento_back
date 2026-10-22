import pytest

from apps.audit.models import AuditLog
from apps.branches.models import Branch

pytestmark = pytest.mark.django_db

URL = "/api/v1/branches/"


def test_owner_sees_all_branches(owner_client, branch, branch2):
    response = owner_client.get(URL)
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 2
    assert set(body) == {"count", "page", "page_size", "total_pages", "results"}
    assert [b["code"] for b in body["results"]] == ["SAM1", "TSH1"]  # nom bo'yicha tartib


def test_seller_sees_only_own_branch(seller_client, branch, branch2):
    body = seller_client.get(URL).json()
    assert [b["id"] for b in body["results"]] == [branch.id]

    assert seller_client.get(f"{URL}{branch.id}/").status_code == 200
    response = seller_client.get(f"{URL}{branch2.id}/")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_seller_cannot_create_or_update(seller_client, branch):
    assert seller_client.post(URL, {"code": "X1", "name": "X"}).status_code == 403
    assert seller_client.patch(f"{URL}{branch.id}/", {"name": "Y"}).status_code == 403


def test_owner_creates_branch_with_audit(owner_client, owner, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        response = owner_client.post(
            URL,
            {"code": "tsh2", "name": "Toshkent 2", "type": "shop", "phone": "+998712000000"},
            HTTP_X_REQUEST_ID="req-abc",
        )
    assert response.status_code == 201, response.json()
    body = response.json()
    assert body["code"] == "TSH2"
    assert body["is_active"] is True

    log = AuditLog.objects.get(event_name="branch.created")
    assert log.actor == owner
    assert log.branch_id == body["id"]
    assert log.aggregate_type == "branch" and log.aggregate_id == body["id"]
    assert log.request_id == "req-abc"
    assert log.ip == "127.0.0.1"
    assert log.payload["code"] == "TSH2"


def test_duplicate_or_invalid_code(owner_client, branch):
    for code in ("tsh1", "TSH1"):
        response = owner_client.post(URL, {"code": code, "name": "X"})
        assert response.status_code == 400
        assert response.json()["error"]["details"] == [
            {"field": "code", "code": "unique", "message": "Bu kod band"}
        ]
    response = owner_client.post(URL, {"code": "TS H", "name": "X"})
    assert response.json()["error"]["details"][0]["code"] == "invalid"


def test_update_emits_changes(owner_client, branch, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        response = owner_client.patch(
            f"{URL}{branch.id}/", {"name": "Toshkent Markaz", "is_active": False}
        )
    assert response.status_code == 200
    branch.refresh_from_db()
    assert branch.name == "Toshkent Markaz" and branch.is_active is False
    changes = AuditLog.objects.get(event_name="branch.updated").payload["changes"]
    assert changes == {
        "name": {"old": "Toshkent 1", "new": "Toshkent Markaz"},
        "is_active": {"old": True, "new": False},
    }


def test_filters_and_search(owner_client, branch, branch2):
    assert owner_client.get(URL, {"type": "warehouse"}).json()["count"] == 1
    assert owner_client.get(URL, {"search": "samar"}).json()["results"][0]["code"] == "SAM1"
    Branch.objects.filter(pk=branch2.pk).update(is_active=False)
    assert owner_client.get(URL, {"is_active": "true"}).json()["count"] == 1


def test_no_delete(owner_client, branch):
    assert owner_client.delete(f"{URL}{branch.id}/").status_code == 405
