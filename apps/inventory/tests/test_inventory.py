"""Qoldiq servislari: kirim, FIFO chiqim, bekor qilish, minimal qoldiq, API va ruxsatlar."""

from decimal import Decimal

import pytest
from django.db import transaction
from django.db.models import Sum

from apps.catalog.models import Product, Unit
from apps.inventory import services
from apps.inventory.costing import get_strategy
from apps.inventory.exceptions import BatchConsumed, InsufficientStock
from apps.inventory.models import Batch, StockLevel, StockMovement
from apps.inventory.types import DocRef, MovementType
from core.models import OutboxEvent

pytestmark = pytest.mark.django_db

D = Decimal


@pytest.fixture
def product(db) -> Product:
    unit = Unit.objects.get(code="dona")
    return Product.objects.create(sku="P1", name="Olma sharbati", unit=unit, min_quantity=D("10"))


def receive(owner, branch, product, qty, cost, doc_id=1, line=1):
    with transaction.atomic():
        return services.receive_stock(
            actor=owner,
            branch_id=branch.id,
            product_id=product.id,
            quantity=D(qty),
            unit_cost_base=D(cost),
            movement_type=MovementType.PURCHASE_IN,
            doc=DocRef(type="purchase", id=doc_id, number=f"K-{doc_id}", line_id=line),
        )


def issue(owner, branch, product, qty, doc_id=100):
    with transaction.atomic():
        return services.issue_stock(
            actor=owner,
            branch_id=branch.id,
            product_id=product.id,
            quantity=D(qty),
            movement_type=MovementType.SALE_OUT,
            doc=DocRef(type="sale", id=doc_id, number=f"S-{doc_id}"),
        )


def assert_invariant(branch, product):
    """StockLevel.quantity == SUM(Batch.quantity_remaining)."""
    level = StockLevel.objects.get(branch=branch, product=product)
    remaining = Batch.objects.filter(branch=branch, product=product).aggregate(
        s=Sum("quantity_remaining")
    )["s"] or D(0)
    assert level.quantity == remaining


# --- kirim ---


def test_receive_creates_batch_movement_level_and_event(owner, branch, product):
    batch = receive(owner, branch, product, "20", "1.25")
    assert batch.quantity_initial == batch.quantity_remaining == D("20")
    assert batch.unit_cost_base == D("1.250000")
    level = StockLevel.objects.get(branch=branch, product=product)
    assert level.quantity == D("20")
    assert level.below_minimum is False
    movement = StockMovement.objects.get()
    assert movement.type == "purchase_in"
    assert movement.quantity == D("20")
    assert movement.total_cost_base == D("25.0000")
    assert movement.balance_after == D("20")
    assert movement.document_number == "K-1"
    event = OutboxEvent.objects.get(name="stock.changed")
    assert event.branch_id == branch.id
    assert event.payload["quantity_after"] == "20.000"
    assert event.payload["delta"] == "20"
    assert_invariant(branch, product)


def test_costing_strategy_registry():
    assert get_strategy().key == "fifo"
    with pytest.raises(KeyError):
        get_strategy("lifo")


# --- FIFO chiqim ---


def test_fifo_issue_takes_oldest_batches_first(owner, branch, product):
    b1 = receive(owner, branch, product, "5", "1.00", doc_id=1)
    b2 = receive(owner, branch, product, "10", "2.00", doc_id=2)
    b3 = receive(owner, branch, product, "10", "3.00", doc_id=3)

    result = issue(owner, branch, product, "12")
    assert [(a.batch_id, a.quantity, a.unit_cost_base) for a in result.allocations] == [
        (b1.id, D("5"), D("1.000000")),
        (b2.id, D("7"), D("2.000000")),
    ]
    assert result.total_cost_base == D("19.0000")  # 5*1 + 7*2
    assert result.unit_cost_base == D("19") / D("12")

    b1.refresh_from_db()
    b2.refresh_from_db()
    b3.refresh_from_db()
    assert (b1.quantity_remaining, b2.quantity_remaining, b3.quantity_remaining) == (
        D("0"),
        D("3"),
        D("10"),
    )
    out = StockMovement.objects.filter(type="sale_out").order_by("id")
    assert [(m.quantity, m.balance_after) for m in out] == [(D("-5"), D("20")), (D("-7"), D("13"))]
    assert StockLevel.objects.get(branch=branch, product=product).quantity == D("13")
    assert_invariant(branch, product)


def test_insufficient_stock_rolls_back_everything(owner, branch, product):
    receive(owner, branch, product, "3", "1")
    with pytest.raises(InsufficientStock) as exc:
        issue(owner, branch, product, "5")
    assert exc.value.status_code == 409
    assert exc.value.details[0]["message"] == "Mavjud: 3"
    assert StockLevel.objects.get(branch=branch, product=product).quantity == D("3")
    assert Batch.objects.get().quantity_remaining == D("3")
    assert StockMovement.objects.filter(type="sale_out").count() == 0


def test_stock_is_per_branch(owner, branch, branch2, product):
    receive(owner, branch, product, "5", "1")
    with pytest.raises(InsufficientStock):
        issue(owner, branch2, product, "1")


def test_below_minimum_event_only_on_crossing(owner, branch, product):
    receive(owner, branch, product, "15", "1")  # min = 10
    issue(owner, branch, product, "3", doc_id=101)  # 12 — hali yuqori
    assert not OutboxEvent.objects.filter(name="stock.below_minimum").exists()
    issue(owner, branch, product, "4", doc_id=102)  # 8 — chegaradan o'tdi
    issue(owner, branch, product, "1", doc_id=103)  # 7 — yana past, qayta xabar yo'q
    events = OutboxEvent.objects.filter(name="stock.below_minimum")
    assert events.count() == 1
    assert events[0].payload["quantity"] == "8.000"
    assert events[0].payload["min_quantity"] == "10.000"
    assert events[0].payload["unit"] == "dona"
    assert StockLevel.objects.get(branch=branch, product=product).below_minimum is True

    receive(owner, branch, product, "10", "1", doc_id=2)  # 17 — tiklandi
    assert StockLevel.objects.get(branch=branch, product=product).below_minimum is False
    issue(owner, branch, product, "10", doc_id=104)  # 7 — yana o'tdi
    assert OutboxEvent.objects.filter(name="stock.below_minimum").count() == 2


# --- kirimni bekor qilish ---


def test_reverse_receipt_untouched(owner, branch, product):
    receive(owner, branch, product, "5", "1", doc_id=7, line=1)
    receive(owner, branch, product, "3", "2", doc_id=7, line=2)
    with transaction.atomic():
        assert services.reverse_receipt(actor=owner, doc_type="purchase", doc_id=7) == 2
    assert StockLevel.objects.get(branch=branch, product=product).quantity == D("0")
    cancels = StockMovement.objects.filter(type="purchase_cancel")
    assert sorted(m.quantity for m in cancels) == [D("-5"), D("-3")]
    assert_invariant(branch, product)


def test_reverse_receipt_after_consumption_is_rejected(owner, branch, product):
    receive(owner, branch, product, "5", "1", doc_id=7)
    issue(owner, branch, product, "1")
    with pytest.raises(BatchConsumed), transaction.atomic():
        services.reverse_receipt(actor=owner, doc_type="purchase", doc_id=7)
    assert StockLevel.objects.get(branch=branch, product=product).quantity == D("4")


# --- API ---


def test_stock_api_scoping_and_cost_visibility(
    owner_client, seller_client, owner, branch, branch2, product
):
    receive(owner, branch, product, "4", "2.5")
    receive(owner, branch2, product, "6", "3", doc_id=2)

    body = owner_client.get("/api/v1/inventory/stock/").json()
    assert body["count"] == 2
    row = next(r for r in body["results"] if r["branch"] == branch.id)
    assert row["quantity"] == "4.000"
    assert row["value_base"] == "10.0000"
    assert row["effective_min"] == "10.000"
    assert row["is_below_min"] is True
    assert row["unit_code"] == "dona"

    body = seller_client.get("/api/v1/inventory/stock/").json()
    assert [r["branch"] for r in body["results"]] == [branch.id]  # faqat o'z nuqtasi
    assert "value_base" not in body["results"][0]  # tannarx yashirilgan

    assert (
        owner_client.get("/api/v1/inventory/stock/", {"below_minimum": "true"}).json()["count"] == 2
    )
    assert owner_client.get("/api/v1/inventory/stock/", {"search": "sharbat"}).json()["count"] == 2
    assert owner_client.get("/api/v1/inventory/stock/", {"branch": branch2.id}).json()["count"] == 1


def test_min_quantity_per_branch(
    owner_client, seller_client, storekeeper, as_user, owner, branch, product
):
    receive(owner, branch, product, "4", "1")
    level = StockLevel.objects.get(branch=branch, product=product)
    url = f"/api/v1/inventory/stock/{level.id}/"

    assert seller_client.patch(url, {"min_quantity": "2"}).status_code == 403
    response = as_user(storekeeper).patch(url, {"min_quantity": "2"})
    assert response.status_code == 200, response.json()
    assert response.json()["effective_min"] == "2.000"
    assert response.json()["is_below_min"] is False

    response = owner_client.patch(url, {"min_quantity": None})  # default ga qaytish
    assert response.json()["effective_min"] == "10.000"
    assert OutboxEvent.objects.filter(name="stock.min_quantity_changed").count() == 2


def test_movements_and_batches_api(owner_client, seller_client, owner, branch, product):
    receive(owner, branch, product, "5", "1.5")
    issue(owner, branch, product, "2")

    body = owner_client.get("/api/v1/inventory/movements/", {"product": product.id}).json()
    assert body["count"] == 2
    latest = body["results"][0]
    assert latest["type"] == "sale_out" and latest["type_display"] == "Savdo"
    assert latest["quantity"] == "-2.000" and latest["total_cost_base"] == "-3.0000"
    assert (
        owner_client.get("/api/v1/inventory/movements/", {"direction": "in"}).json()["count"] == 1
    )
    assert (
        owner_client.get("/api/v1/inventory/movements/", {"type": "purchase_in"}).json()["count"]
        == 1
    )

    seller_body = seller_client.get("/api/v1/inventory/movements/").json()
    assert seller_body["count"] == 2
    assert "unit_cost_base" not in seller_body["results"][0]

    batches = owner_client.get(
        "/api/v1/inventory/batches/", {"product": product.id, "open": "true"}
    )
    assert batches.status_code == 200
    assert batches.json()["results"][0]["quantity_remaining"] == "3.000"
    assert seller_client.get("/api/v1/inventory/batches/").status_code == 403  # tannarx huquqi yo'q


def test_stock_api_hidden_from_other_branch(seller_client, owner, branch2, product):
    receive(owner, branch2, product, "4", "1")
    level = StockLevel.objects.get(branch=branch2, product=product)
    assert seller_client.get(f"/api/v1/inventory/stock/{level.id}/").status_code == 404
