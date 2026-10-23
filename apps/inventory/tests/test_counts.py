"""Inventarizatsiya: ro'yxat, sanash, yakunlash (ortiqcha/kamomad), bekor qilish, ruxsatlar."""

from decimal import Decimal

import pytest
from django.db import transaction

from apps.inventory import services
from apps.inventory.models import Batch, StockCount, StockMovement
from apps.inventory.types import DocRef, MovementType
from core.models import OutboxEvent

from .conftest import assert_invariant, qty

pytestmark = pytest.mark.django_db

D = Decimal
URL = "/api/v1/inventory/counts/"


@pytest.fixture
def stocked(branch, branch2, goods, stock_in):
    stock_in(branch, goods["cola"], "10", "1")
    stock_in(branch, goods["cola"], "10", "2")
    stock_in(branch, goods["fanta"], "5", "3")
    stock_in(branch2, goods["sugar"], "4", "7.5")  # boshqa nuqta — ortiqcha tannarxi uchun


def open_count(client, branch, **extra):
    response = client.post(URL, {"branch": branch.id, **extra}, format="json")
    assert response.status_code == 201, response.json()
    return response.json()


def items(client, count_id, **params):
    return client.get(f"{URL}{count_id}/items/", params).json()


def test_create_lists_stock_and_blocks_second(sk_client, branch, goods, stocked):
    data = open_count(sk_client, branch)
    assert data["number"].startswith("INV-TSH1-") and data["status"] == "draft"
    assert (data["items_count"], data["counted_count"]) == (2, 0)
    rows = items(sk_client, data["id"])["results"]
    assert [(r["product_name"], r["expected_quantity"]) for r in rows] == [
        ("Coca-Cola 1L", "20.000"),
        ("Fanta 1L", "5.000"),
    ]
    second = sk_client.post(URL, {"branch": branch.id}, format="json")
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "count_in_progress"


def test_complete_adjusts_stock(sk_client, owner, branch, goods, stocked):
    data = open_count(sk_client, branch)
    response = sk_client.post(
        f"{URL}{data['id']}/counted/",
        {
            "items": [
                {"product": goods["cola"].id, "counted_quantity": "17"},  # kamomad 3
                {"product": goods["sugar"].id, "counted_quantity": "2.5"},  # ro'yxatda yo'q edi
            ]
        },
        format="json",
    )
    assert response.status_code == 200, response.json()
    assert (response.json()["items_count"], response.json()["counted_count"]) == (3, 2)
    assert [
        r["product_name"] for r in items(sk_client, data["id"], state="uncounted")["results"]
    ] == ["Fanta 1L"]
    diff = items(sk_client, data["id"], state="diff")["results"]
    assert {r["product_name"]: r["current_quantity"] for r in diff} == {
        "Coca-Cola 1L": "20.000",
        "Shakar": "0.000",
    }

    # sanash davomida savdo bo'ldi: yakunlashda joriy qoldiq bilan solishtiriladi
    with transaction.atomic():
        services.issue_stock(
            actor=owner,
            branch_id=branch.id,
            product_id=goods["cola"].id,
            quantity=D("1"),
            movement_type=MovementType.SALE_OUT,
            doc=DocRef(type="sale", id=1, number="S-1"),
        )

    done = sk_client.post(f"{URL}{data['id']}/complete/")
    assert done.status_code == 200, done.json()
    body = done.json()
    assert body["status"] == "completed" and body["completed_by_name"] == "Omborchi"
    # cola: hisobda 19, sanalgan 17 → kamomad 2 (FIFO: 1-partiyadan 2×1 = 2)
    # shakar: 0 → 2,5 ortiqcha, tannarx — oxirgi partiya (boshqa nuqta) 7,5 → 18,75
    assert D(body["shortage_cost_base"]) == D("2") and D(body["surplus_cost_base"]) == D("18.75")
    assert qty(branch, goods["cola"]) == D("17")
    assert qty(branch, goods["fanta"]) == D("5")  # sanalmagan — o'zgarmadi
    assert qty(branch, goods["sugar"]) == D("2.5")
    surplus = Batch.objects.get(branch=branch, product=goods["sugar"])
    assert (surplus.source_type, surplus.unit_cost_base) == ("stock_count", D("7.5"))
    types = set(StockMovement.objects.filter(document_type="stock_count").values_list("type"))
    assert types == {("count_shortage",), ("count_surplus",)}
    rows = {r["product_name"]: r for r in items(sk_client, data["id"])["results"]}
    assert (rows["Coca-Cola 1L"]["expected_quantity"], rows["Coca-Cola 1L"]["difference"]) == (
        "19.000",
        "-2.000",
    )
    assert rows["Fanta 1L"]["difference"] == "0.000"
    for p in ("cola", "fanta", "sugar"):
        assert_invariant(branch, goods[p])
    event = OutboxEvent.objects.get(name="stock_count.completed")
    assert (event.payload["surplus_items"], event.payload["shortage_items"]) == (1, 1)
    # yakunlangan — o'zgarmaydi; yangi inventarizatsiya ochish mumkin
    assert sk_client.post(f"{URL}{data['id']}/complete/").status_code == 409
    open_count(sk_client, branch)


def test_nothing_counted_and_cancel(sk_client, branch, goods, stocked):
    data = open_count(sk_client, branch)
    empty = sk_client.post(f"{URL}{data['id']}/complete/")
    assert empty.status_code == 409 and empty.json()["error"]["code"] == "count_empty"
    sk_client.post(
        f"{URL}{data['id']}/counted/",
        {"items": [{"product": goods["cola"].id, "counted_quantity": "1"}]},
        format="json",
    )
    cancelled = sk_client.post(f"{URL}{data['id']}/cancel/")
    assert cancelled.json()["status"] == "cancelled"
    assert qty(branch, goods["cola"]) == D("20")
    edit = sk_client.post(
        f"{URL}{data['id']}/counted/",
        {"items": [{"product": goods["cola"].id, "counted_quantity": "2"}]},
        format="json",
    )
    assert edit.status_code == 409


def test_counted_validation_and_reset(sk_client, branch, goods, stocked):
    data = open_count(sk_client, branch)
    bad = sk_client.post(
        f"{URL}{data['id']}/counted/",
        {"items": [{"product": goods["cola"].id, "counted_quantity": "1.5"}]},
        format="json",
    )
    assert bad.status_code == 400
    assert bad.json()["error"]["details"][0]["field"] == "items.0.counted_quantity"
    sk_client.post(
        f"{URL}{data['id']}/counted/",
        {"items": [{"product": goods["cola"].id, "counted_quantity": "3"}]},
        format="json",
    )
    reset = sk_client.post(
        f"{URL}{data['id']}/counted/",
        {"items": [{"product": goods["cola"].id, "counted_quantity": None}]},
        format="json",
    )
    assert reset.json()["counted_count"] == 0


def test_category_and_search(sk_client, branch, goods, stocked):
    from apps.catalog.models import Category

    drinks = Category.objects.create(name="Ichimliklar")
    goods["fanta"].category = drinks
    goods["fanta"].save()
    data = open_count(sk_client, branch, category=drinks.id)
    assert data["items_count"] == 1 and data["category_name"] == "Ichimliklar"
    sk_client.post(f"{URL}{data['id']}/cancel/")
    data = open_count(sk_client, branch)
    found = items(sk_client, data["id"], search="cola")["results"]
    assert [r["product_name"] for r in found] == ["Coca-Cola 1L"]


def test_permissions_and_branch_scope(seller_client, sk2_client, sk_client, branch, goods, stocked):
    assert seller_client.get(URL).status_code == 403
    alien = sk2_client.post(URL, {"branch": branch.id}, format="json")
    assert alien.status_code == 403
    data = open_count(sk_client, branch)
    assert sk2_client.get(f"{URL}{data['id']}/").status_code == 404
    assert StockCount.objects.count() == 1
