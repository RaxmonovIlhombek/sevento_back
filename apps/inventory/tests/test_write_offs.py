"""Hisobdan chiqarish: FIFO chiqim va tannarx, bekor qilish, sabablar, ruxsatlar."""

from decimal import Decimal

import pytest

from apps.inventory.models import StockMovement, WriteOff, WriteOffReason

from .conftest import assert_invariant, qty

pytestmark = pytest.mark.django_db

D = Decimal
URL = "/api/v1/inventory/write-offs/"
REASONS = "/api/v1/inventory/write-off-reasons/"


@pytest.fixture
def stocked(branch, goods, stock_in):
    stock_in(branch, goods["cola"], "10", "1")
    stock_in(branch, goods["cola"], "10", "2")
    stock_in(branch, goods["fanta"], "5", "3")


def reason(code):
    return WriteOffReason.objects.get(code=code)


def body(branch, items, code="damaged", **extra):
    return {
        "branch": branch.id,
        "reason": reason(code).id,
        "items": [{"product": p.id, "quantity": q} for p, q in items],
        **extra,
    }


def test_create_issues_fifo(sk_client, branch, goods, stocked):
    response = sk_client.post(
        URL,
        body(branch, [(goods["cola"], "12"), (goods["fanta"], "1")], note="Suv tegdi"),
        format="json",
    )
    assert response.status_code == 201, response.json()
    data = response.json()
    assert data["status"] == "completed" and data["number"].startswith("HC-TSH1-")
    assert data["reason_name"] == "Buzilgan / shikastlangan"
    assert D(data["total_cost_base"]) == D("17")  # 10×1 + 2×2 + 1×3
    assert data["can_cancel"] is True
    assert qty(branch, goods["cola"]) == D("8")
    assert StockMovement.objects.filter(type="write_off").count() == 3
    assert_invariant(branch, goods["cola"])


def test_insufficient_rolls_back(sk_client, branch, goods, stocked):
    response = sk_client.post(
        URL, body(branch, [(goods["cola"], "1"), (goods["fanta"], "6")]), format="json"
    )
    assert response.status_code == 409
    assert response.json()["error"]["details"][0]["field"] == "items.1.quantity"
    assert WriteOff.objects.count() == 0 and qty(branch, goods["cola"]) == D("20")


def test_cancel_restores(sk_client, branch, goods, stocked):
    data = sk_client.post(URL, body(branch, [(goods["cola"], "12")]), format="json").json()
    response = sk_client.post(f"{URL}{data['id']}/cancel/", {"reason": "Xato"}, format="json")
    assert response.status_code == 200, response.json()
    assert response.json()["status"] == "cancelled" and response.json()["can_cancel"] is False
    assert qty(branch, goods["cola"]) == D("20")
    assert StockMovement.objects.filter(type="write_off_cancel").count() == 2
    assert_invariant(branch, goods["cola"])
    again = sk_client.post(f"{URL}{data['id']}/cancel/", {"reason": "x"}, format="json")
    assert again.status_code == 409


def test_system_reason_not_selectable(sk_client, branch, goods, stocked):
    response = sk_client.post(
        URL, body(branch, [(goods["cola"], "1")], code="transfer_shortage"), format="json"
    )
    assert response.status_code == 400
    assert response.json()["error"]["details"][0]["field"] == "reason"


def test_transfer_shortage_not_cancellable(
    sk_client, owner_client, branch, branch2, goods, stocked
):
    transfer = sk_client.post(
        "/api/v1/inventory/transfers/",
        {
            "from_branch": branch.id,
            "to_branch": branch2.id,
            "items": [{"product": goods["cola"].id, "quantity": "2"}],
        },
        format="json",
    ).json()
    sent = sk_client.post(f"/api/v1/inventory/transfers/{transfer['id']}/send/").json()
    owner_client.post(
        f"/api/v1/inventory/transfers/{transfer['id']}/receive/",
        {"items": [{"id": sent["items"][0]["id"], "quantity_received": "1"}]},
        format="json",
    )
    write_off = WriteOff.objects.get(transfer_id=transfer["id"])
    detail = owner_client.get(f"{URL}{write_off.pk}/").json()
    assert detail["can_cancel"] is False and detail["transfer_number"] == transfer["number"]
    response = owner_client.post(f"{URL}{write_off.pk}/cancel/", {"reason": "x"}, format="json")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "write_off_system"


def test_reasons_reference(sk_client, owner_client):
    rows = sk_client.get(REASONS, {"is_system": "false"}).json()
    assert {r["code"] for r in rows} == {"damaged", "expired", "lost", "internal", "other"}
    assert sk_client.post(REASONS, {"code": "rats", "name": "Kemiruvchi"}).status_code == 403
    created = owner_client.post(REASONS, {"code": "Rats", "name": "Kemiruvchilar"}, format="json")
    assert created.status_code == 201 and created.json()["code"] == "rats"
    dup = owner_client.post(REASONS, {"code": "rats", "name": "x"}, format="json")
    assert dup.status_code == 400


def test_permissions_and_filters(seller_client, sk_client, sk2_client, branch, goods, stocked):
    assert seller_client.get(URL).status_code == 403
    sk_client.post(URL, body(branch, [(goods["cola"], "1")]), format="json")
    sk_client.post(URL, body(branch, [(goods["cola"], "1")], code="expired"), format="json")
    assert sk_client.get(URL, {"reason": reason("expired").id}).json()["count"] == 1
    assert sk2_client.get(URL).json()["count"] == 0  # begona nuqta
    alien = sk2_client.post(URL, body(branch, [(goods["cola"], "1")]), format="json")
    assert alien.status_code == 403
