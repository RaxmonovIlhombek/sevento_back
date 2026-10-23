"""Savdo: narx, chegirma, FIFO chiqim, to'lov va qaytim, kassa, bekor qilish, chek, ruxsatlar."""

from decimal import Decimal

import pytest
from django.db.models import F

from apps.audit.models import AuditLog
from apps.inventory.models import Batch, StockLevel, StockMovement
from apps.payments.models import Cashbox, CashTransaction, Payment
from apps.sales.models import Sale
from core import settings_service

from .conftest import sale_payload

pytestmark = pytest.mark.django_db

D = Decimal
URL = "/api/v1/sales/"


def cola_sugar(products, cola="12", sugar="1.5", **discounts):
    return [
        {"product": products["cola"].id, "quantity": cola, **discounts.get("cola", {})},
        {"product": products["sugar"].id, "quantity": sugar},
    ]


def balance(branch, code) -> Decimal:
    box = Cashbox.objects.filter(branch=branch, currency__code=code).first()
    return box.balance if box else D(0)


def test_cash_sale_with_change(
    seller_client, branch, uzs, products, stocked, cash, django_capture_on_commit_callbacks
):
    # cola 12 × 10 000 = 120 000; shakar 1,5 kg × 15 000 (1,20 USD × 12 500) = 22 500
    body = sale_payload(
        branch,
        uzs,
        cola_sugar(products),
        [{"method": cash.id, "currency": uzs.id, "amount": "150000"}],
        expected_total="142500",
    )
    with django_capture_on_commit_callbacks(execute=True):
        response = seller_client.post(URL, body, format="json")
    assert response.status_code == 201, response.json()
    data = response.json()
    assert data["number"] == "S-TSH1-26-000001" or data["number"].startswith("S-TSH1-")
    assert D(data["total"]) == D("142500")
    assert D(data["change_amount"]) == D("7500")
    assert [D(i["unit_price"]) for i in data["items"]] == [D("10000"), D("15000")]
    assert data["cost_base"] is None and data["profit_base"] is None  # sotuvchi tannarxni ko'rmaydi
    assert data["items"][0]["cost_base"] is None
    assert [(p["kind"], D(p["amount"])) for p in data["payments"]] == [
        ("payment", D("150000")),
        ("change", D("7500")),
    ]

    sale = Sale.objects.get(pk=data["id"])
    # FIFO: 10 × 0,60 + 2 × 0,70 = 7,40; shakar 1,5 × 0,80 = 1,20
    assert sale.cost_base == D("8.6000")
    assert sale.total_base == D("11.4000")  # 142 500 / 12 500
    assert StockLevel.objects.get(branch=branch, product=products["cola"]).quantity == D("8")
    stocked["cola1"].refresh_from_db()
    stocked["cola2"].refresh_from_db()
    assert (stocked["cola1"].quantity_remaining, stocked["cola2"].quantity_remaining) == (0, 8)
    outs = StockMovement.objects.filter(document_type="sale", document_id=sale.pk)
    assert outs.filter(type="sale_out").count() == 3  # cola 2 partiyadan + shakar
    # kassa: +150 000 −7 500
    assert balance(branch, "UZS") == D("142500")
    assert CashTransaction.objects.filter(cashbox__branch=branch).count() == 2
    assert AuditLog.objects.filter(event_name="sale.completed", aggregate_id=sale.pk).exists()
    assert AuditLog.objects.filter(event_name="payment.received").count() == 1


def test_mixed_currency_and_card(seller_client, branch, uzs, usd, products, stocked, cash, card):
    # 142 500 = 10 USD naqd (125 000) + 17 500 so'm karta
    body = sale_payload(
        branch,
        uzs,
        cola_sugar(products),
        [
            {"method": cash.id, "currency": usd.id, "amount": "10"},
            {"method": card.id, "currency": uzs.id, "amount": "17500"},
        ],
    )
    response = seller_client.post(URL, body, format="json")
    assert response.status_code == 201, response.json()
    assert D(response.json()["change_amount"]) == 0
    assert balance(branch, "USD") == D("10")
    assert balance(branch, "UZS") == 0  # karta kassaga tushmaydi
    payments = Payment.objects.filter(document_type="sale")
    assert {p.method.code: p.amount_base for p in payments} == {
        "cash": D("10.0000"),
        "card": D("1.4000"),
    }


def test_change_needs_cash_in_drawer(seller_client, branch, uzs, usd, products, stocked, cash):
    # cola 12 = 120 000; 10 USD (125 000) → qaytim 5 000 so'm, lekin so'm kassasi bo'sh
    items = [{"product": products["cola"].id, "quantity": "12"}]
    pay_usd = [{"method": cash.id, "currency": usd.id, "amount": "10"}]
    response = seller_client.post(URL, sale_payload(branch, uzs, items, pay_usd), format="json")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "insufficient_cash"
    assert Sale.objects.count() == 0
    assert StockLevel.objects.get(branch=branch, product=products["cola"]).quantity == 20

    # avval so'mda naqd savdo (kassada 10 000 bo'ladi), keyin qaytim beriladi
    one = [{"product": products["cola"].id, "quantity": "1"}]
    pay_uzs = [{"method": cash.id, "currency": uzs.id, "amount": "10000"}]
    assert (
        seller_client.post(URL, sale_payload(branch, uzs, one, pay_uzs), format="json").status_code
        == 201
    )
    response = seller_client.post(URL, sale_payload(branch, uzs, items, pay_usd), format="json")
    assert response.status_code == 201, response.json()
    assert balance(branch, "UZS") == D("5000")
    assert balance(branch, "USD") == D("10")


def test_payment_insufficient(seller_client, branch, uzs, products, stocked, cash):
    body = sale_payload(
        branch,
        uzs,
        cola_sugar(products),
        [{"method": cash.id, "currency": uzs.id, "amount": "100000"}],
    )
    response = seller_client.post(URL, body, format="json")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "payment_insufficient"
    assert not StockMovement.objects.filter(type="sale_out").exists()


def test_card_overpayment_rejected(seller_client, branch, uzs, products, stocked, card):
    body = sale_payload(
        branch,
        uzs,
        cola_sugar(products),
        [{"method": card.id, "currency": uzs.id, "amount": "150000"}],
    )
    response = seller_client.post(URL, body, format="json")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "change_not_cash"


def test_insufficient_stock_rolls_back(seller_client, branch, uzs, products, stocked, cash):
    body = sale_payload(
        branch,
        uzs,
        [
            {"product": products["sugar"].id, "quantity": "1"},
            {"product": products["cola"].id, "quantity": "25"},
        ],
        [{"method": cash.id, "currency": uzs.id, "amount": "300000"}],
    )
    response = seller_client.post(URL, body, format="json")
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "insufficient_stock"
    assert error["details"][0]["field"] == "items.1.quantity"
    assert "20" in error["details"][0]["message"]
    assert Sale.objects.count() == 0 and Payment.objects.count() == 0
    assert StockLevel.objects.get(branch=branch, product=products["sugar"]).quantity == 5


def test_price_missing_and_conversion_setting(
    django_capture_on_commit_callbacks, owner, seller_client, branch, uzs, products, stocked, cash
):
    pay = [{"method": cash.id, "currency": uzs.id, "amount": "100000"}]
    body = sale_payload(branch, uzs, [{"product": products["noprice"].id, "quantity": "1"}], pay)
    response = seller_client.post(URL, body, format="json")
    assert response.status_code == 400
    assert response.json()["error"]["details"][0]["code"] == "price_missing"

    with django_capture_on_commit_callbacks(execute=True):  # kesh commit dan keyin tozalanadi
        settings_service.set(key="sales.convert_missing_price", value=False, actor=owner)
    body = sale_payload(branch, uzs, [{"product": products["sugar"].id, "quantity": "1"}], pay)
    response = seller_client.post(URL, body, format="json")
    assert response.status_code == 400
    assert response.json()["error"]["details"][0]["field"] == "items.0.product"


def test_unit_precision(seller_client, branch, uzs, products, stocked, cash):
    body = sale_payload(
        branch,
        uzs,
        [{"product": products["cola"].id, "quantity": "1.5"}],
        [{"method": cash.id, "currency": uzs.id, "amount": "20000"}],
    )
    response = seller_client.post(URL, body, format="json")
    assert response.status_code == 400
    assert response.json()["error"]["details"][0]["code"] == "unit_precision"


def test_discount_limits(
    seller_client, owner_client, roles, branch, uzs, products, stocked, cash, as_user
):
    pay = [{"method": cash.id, "currency": uzs.id, "amount": "100000"}]

    def items(discount):
        return [{"product": products["cola"].id, "quantity": "2", "discount_amount": discount}]

    # sotuvchi: 10% gacha (20 000 dan 2 000)
    ok = seller_client.post(URL, sale_payload(branch, uzs, items("2000"), pay), format="json")
    assert ok.status_code == 201, ok.json()
    assert D(ok.json()["total"]) == D("18000")
    assert D(ok.json()["discount_total"]) == D("2000")
    too_big = seller_client.post(URL, sale_payload(branch, uzs, items("3000"), pay), format="json")
    assert too_big.status_code == 400
    assert too_big.json()["error"]["code"] == "discount_limit"
    # rahbar — cheksiz
    assert (
        owner_client.post(
            URL, sale_payload(branch, uzs, items("10000"), pay), format="json"
        ).status_code
        == 201
    )
    # chegirma huquqisiz rol
    roles["seller"].capabilities = [
        c for c in roles["seller"].capabilities if c != "sales.discount"
    ]
    roles["seller"].save()
    from apps.accounts.models import User

    plain = User.objects.get(username="sotuvchi")
    response = as_user(plain).post(URL, sale_payload(branch, uzs, items("100"), pay), format="json")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "discount_forbidden"


def test_expected_total_mismatch(seller_client, branch, uzs, products, stocked, cash):
    body = sale_payload(
        branch,
        uzs,
        cola_sugar(products),
        [{"method": cash.id, "currency": uzs.id, "amount": "150000"}],
        expected_total="140000",
    )
    response = seller_client.post(URL, body, format="json")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "total_mismatch"


def test_idempotent_create(seller_client, branch, uzs, products, stocked, cash):
    body = sale_payload(
        branch,
        uzs,
        [{"product": products["cola"].id, "quantity": "1"}],
        [{"method": cash.id, "currency": uzs.id, "amount": "10000"}],
    )
    first = seller_client.post(URL, body, format="json", HTTP_IDEMPOTENCY_KEY="sale-1")
    second = seller_client.post(URL, body, format="json", HTTP_IDEMPOTENCY_KEY="sale-1")
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert Sale.objects.count() == 1
    assert StockLevel.objects.get(branch=branch, product=products["cola"]).quantity == 19


def test_branch_scope(seller_client, owner_client, branch, branch2, uzs, products, stocked, cash):
    pay = [{"method": cash.id, "currency": uzs.id, "amount": "10000"}]
    one = [{"product": products["cola"].id, "quantity": "1"}]
    response = seller_client.post(URL, sale_payload(branch2, uzs, one, pay), format="json")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "branch_forbidden"

    assert (
        owner_client.post(URL, sale_payload(branch, uzs, one, pay), format="json").status_code
        == 201
    )
    assert len(seller_client.get(URL).json()["results"]) == 1
    sale_id = Sale.objects.get().pk
    # boshqa nuqta sotuvchisi ko'rmaydi
    from rest_framework.test import APIClient

    from apps.accounts.models import Role, User, UserBranch
    from apps.accounts.services import issue_tokens

    other = User.objects.create_user(
        username="sotuvchi2", password="x", full_name="S2", role=Role.objects.get(code="seller")
    )
    UserBranch.objects.create(user=other, branch=branch2, is_default=True)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_tokens(other)[0]}")
    assert client.get(URL).json()["results"] == []
    assert client.get(f"{URL}{sale_id}/").status_code == 404


def test_owner_sees_cost_and_profit(owner_client, branch, uzs, products, stocked, cash):
    body = sale_payload(
        branch,
        uzs,
        cola_sugar(products),
        [{"method": cash.id, "currency": uzs.id, "amount": "142500"}],
    )
    data = owner_client.post(URL, body, format="json").json()
    assert D(data["cost_base"]) == D("8.6")
    assert D(data["profit_base"]) == D("2.8")
    assert D(data["items"][0]["cost_base"]) == D("7.4")
    assert data["can_cancel"] is True


def test_cancel_restores_batches_and_cash(
    owner_client, seller_client, branch, uzs, products, stocked, cash
):
    body = sale_payload(
        branch,
        uzs,
        cola_sugar(products),
        [{"method": cash.id, "currency": uzs.id, "amount": "150000"}],
    )
    sale_id = seller_client.post(URL, body, format="json").json()["id"]
    assert seller_client.get(f"{URL}{sale_id}/").json()["can_cancel"] is False
    assert (
        seller_client.post(f"{URL}{sale_id}/cancel/", {"reason": "x"}, format="json").status_code
        == 403
    )

    response = owner_client.post(
        f"{URL}{sale_id}/cancel/", {"reason": "Xato urildi"}, format="json"
    )
    assert response.status_code == 200, response.json()
    data = response.json()
    assert data["status"] == "cancelled" and data["cancel_reason"] == "Xato urildi"
    kinds = sorted((p["kind"], p["status"]) for p in data["payments"])
    assert kinds == [
        ("change", "reversed"),
        ("change_return", "completed"),
        ("payment", "reversed"),
        ("refund", "completed"),
    ]
    for key, qty in (("cola1", 10), ("cola2", 10), ("sugar", 5)):
        stocked[key].refresh_from_db()
        assert stocked[key].quantity_remaining == qty
    assert StockLevel.objects.get(branch=branch, product=products["cola"]).quantity == 20
    assert StockMovement.objects.filter(document_id=sale_id, type="sale_cancel").count() == 3
    assert balance(branch, "UZS") == 0
    assert not Batch.objects.filter(quantity_remaining__gt=F("quantity_initial")).exists()

    again = owner_client.post(f"{URL}{sale_id}/cancel/", {"reason": "x"}, format="json")
    assert again.status_code == 409


def test_receipt_pdf(seller_client, branch, uzs, products, stocked, cash):
    body = sale_payload(
        branch,
        uzs,
        cola_sugar(products),
        [{"method": cash.id, "currency": uzs.id, "amount": "150000"}],
    )
    sale_id = seller_client.post(URL, body, format="json").json()["id"]
    response = seller_client.get(f"{URL}{sale_id}/receipt/")
    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    pdf = response.content
    assert pdf.startswith(b"%PDF")
    assert any(name in pdf_objects(pdf) for name in (b"DejaVu", b"Noto"))  # shrift ichida


def pdf_objects(pdf: bytes) -> bytes:
    """PDF dagi siqilgan oqimlarni ochib birlashtiradi (shrift nomini topish uchun)."""
    import re
    import zlib

    chunks = [pdf]
    for match in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", pdf, re.S):
        try:
            chunks.append(zlib.decompress(match.group(1)))
        except zlib.error:
            pass
    return b"".join(chunks)


def test_receipt_context_uzbek_format(seller, branch, uzs, products, stocked, cash, seller_client):
    from apps.sales import selectors
    from apps.sales.receipt import build_context

    body = sale_payload(
        branch,
        uzs,
        cola_sugar(products),
        [{"method": cash.id, "currency": uzs.id, "amount": "150000"}],
    )
    sale_id = seller_client.post(URL, body, format="json").json()["id"]
    sale = Sale.objects.get(pk=sale_id)
    ctx = build_context(sale, selectors.sale_payments(sale))
    assert ctx["total"] == "142 500"
    assert ctx["change"] == "7 500"
    assert ctx["items"][1]["quantity"] == "1,500"
    assert ctx["payments"] == [{"method": "Naqd pul", "amount": "150 000", "currency": "UZS"}]
    assert ctx["footer"] == "Xaridingiz uchun rahmat!"


def test_pos_products(seller_client, branch, uzs, usd, products, stocked):
    response = seller_client.get(
        f"{URL}pos-products/", {"branch": branch.id, "currency": "UZS", "search": "sha"}
    )
    assert response.status_code == 200, response.json()
    [row] = response.json()
    assert row["name"] == "Shakar" and D(row["price"]) == D("15000") and D(row["stock"]) == 5
    by_barcode = seller_client.get(
        f"{URL}pos-products/", {"branch": branch.id, "currency": "USD", "barcode": "4780001"}
    ).json()
    assert [r["sku"] for r in by_barcode] == ["COLA"]
    assert D(by_barcode[0]["price"]) == D("0.80")  # 10 000 / 12 500
    ids = f"{products['cola'].id},{products['sugar'].id}"
    by_ids = seller_client.get(
        f"{URL}pos-products/", {"branch": branch.id, "currency": "UZS", "ids": ids}
    ).json()
    assert sorted(r["sku"] for r in by_ids) == ["COLA", "SUGAR"]


def test_pos_config(seller_client, owner_client, storekeeper, as_user):
    assert seller_client.get(f"{URL}pos-config/").json() == {
        "default_currency": "UZS",
        "max_discount_percent": "10.00",
    }
    assert owner_client.get(f"{URL}pos-config/").json()["max_discount_percent"] is None
    assert as_user(storekeeper).get(f"{URL}pos-config/").status_code == 403


def test_pos_products_branch_forbidden(seller_client, branch2, products):
    response = seller_client.get(f"{URL}pos-products/", {"branch": branch2.id, "currency": "UZS"})
    assert response.status_code == 403


def test_daily_summary(owner_client, seller_client, branch, uzs, products, stocked, cash):
    pay = [{"method": cash.id, "currency": uzs.id, "amount": "142500"}]
    seller_client.post(URL, sale_payload(branch, uzs, cola_sugar(products), pay), format="json")
    data = owner_client.get(f"{URL}summary/").json()
    assert data["count"] == 1
    assert data["by_currency"] == [{"currency": "UZS", "count": 1, "total": "142500.0000"}]
    assert D(data["profit_base"]) == D("2.8")
    assert data["base_currency"] == "USD"
    seller_view = seller_client.get(f"{URL}summary/").json()
    assert seller_view["count"] == 1 and seller_view["profit_base"] is None


def test_storekeeper_cannot_sell(storekeeper, as_user, branch, uzs, products, stocked, cash):
    client = as_user(storekeeper)
    body = sale_payload(
        branch,
        uzs,
        [{"product": products["cola"].id, "quantity": "1"}],
        [{"method": cash.id, "currency": uzs.id, "amount": "10000"}],
    )
    assert client.post(URL, body, format="json").status_code == 403
