"""Nasiyali savdo: mijoz, kredit limiti (409), qisman/to'liq nasiya, bekor qilish, chek."""

from decimal import Decimal

import pytest
from django.utils import timezone

from apps.inventory.models import StockLevel
from apps.payments import services as payment_services
from apps.payments.models import Customer, CustomerLedgerEntry, Debt
from apps.sales.models import Sale

from .conftest import sale_payload

pytestmark = pytest.mark.django_db

D = Decimal
URL = "/api/v1/sales/"


@pytest.fixture
def customer(db):
    # limit 100 USD (asosiy valyuta), muddat 15 kun
    return Customer.objects.create(
        name="Aliyev Vali", phone="+998901112233", credit_limit_base=D("100"), default_due_days=15
    )


def cola(products, qty="12"):
    return [{"product": products["cola"].id, "quantity": qty}]


def test_partial_credit_sale(seller_client, branch, uzs, products, stocked, cash, customer):
    # 12 × 10 000 = 120 000; 20 000 naqd, 100 000 nasiya (8 USD — limit 100 ichida)
    body = sale_payload(
        branch,
        uzs,
        cola(products),
        [{"method": cash.id, "currency": uzs.id, "amount": "20000"}],
        customer=customer.id,
    )
    response = seller_client.post(URL, body, format="json")
    assert response.status_code == 201, response.json()
    data = response.json()
    assert D(data["debt_amount"]) == D("100000")
    assert data["customer_name"] == "Aliyev Vali"
    assert data["debt"]["status"] == "open" and D(data["debt"]["remaining"]) == D("100000")
    debt = Debt.objects.get()
    assert debt.currency.code == "UZS" and debt.document_number == data["number"]
    # muddat mahalliy sanadan (Toshkent) — UTC sanasi kechqurun bir kun orqada bo'ladi
    assert (debt.due_date - timezone.localdate(debt.created_at)).days == 15
    entry = CustomerLedgerEntry.objects.get(customer=customer)
    assert (entry.type, entry.amount, entry.balance_after) == ("debt", D("100000"), D("100000"))
    assert payment_services.open_debts_base(customer.id) == D("8.0000")
    assert Sale.objects.get(pk=data["id"]).due_date == debt.due_date
    assert StockLevel.objects.get(branch=branch, product=products["cola"]).quantity == 8


def test_full_credit_without_payments(seller_client, branch, uzs, products, stocked, customer):
    body = sale_payload(branch, uzs, cola(products, "1"), [], customer=customer.id)
    response = seller_client.post(URL, body, format="json")
    assert response.status_code == 201, response.json()
    assert D(response.json()["debt_amount"]) == D("10000")
    assert response.json()["payments"] == []


def test_credit_limit_exceeded(seller_client, branch, uzs, products, stocked, customer):
    customer.credit_limit_base = D("5")  # 5 USD = 62 500 so'm
    customer.save()
    body = sale_payload(branch, uzs, cola(products), [], customer=customer.id)
    response = seller_client.post(URL, body, format="json")
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "credit_limit_exceeded"
    assert {d["field"] for d in error["details"]} == {"limit_base", "used_base", "requested_base"}
    assert Sale.objects.count() == 0 and Debt.objects.count() == 0
    assert StockLevel.objects.get(branch=branch, product=products["cola"]).quantity == 20


def test_default_limit_zero_blocks_credit(seller_client, branch, uzs, products, stocked):
    walk_in = Customer.objects.create(name="Yangi mijoz")  # limit — sozlama (0)
    body = sale_payload(branch, uzs, cola(products, "1"), [], customer=walk_in.id)
    assert seller_client.post(URL, body, format="json").json()["error"]["code"] == (
        "credit_limit_exceeded"
    )


def test_credit_needs_capability(roles, seller, as_user, branch, uzs, products, stocked, customer):
    roles["seller"].capabilities = [c for c in roles["seller"].capabilities if c != "sales.credit"]
    roles["seller"].save()
    from apps.accounts.models import User

    client = as_user(User.objects.get(username="sotuvchi"))
    body = sale_payload(branch, uzs, cola(products, "1"), [], customer=customer.id)
    response = client.post(URL, body, format="json")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "credit_forbidden"


def test_paid_sale_keeps_customer_history(
    seller_client, branch, uzs, products, stocked, cash, customer
):
    body = sale_payload(
        branch,
        uzs,
        cola(products, "1"),
        [{"method": cash.id, "currency": uzs.id, "amount": "10000"}],
        customer=customer.id,
    )
    data = seller_client.post(URL, body, format="json").json()
    assert data["customer"] == customer.id and D(data["debt_amount"]) == 0 and data["debt"] is None
    assert seller_client.get(URL, {"customer": customer.id}).json()["count"] == 1


def test_credit_warning_on_crossing(
    seller_client, branch, uzs, products, stocked, customer, django_capture_on_commit_callbacks
):
    from apps.audit.models import AuditLog

    # 80% = 80 USD = 1 000 000 so'm; birinchi savdo 8 USD — ogohlantirish yo'q
    with django_capture_on_commit_callbacks(execute=True):
        seller_client.post(
            URL,
            sale_payload(branch, uzs, cola(products, "10"), [], customer=customer.id),
            format="json",
        )
    assert not AuditLog.objects.filter(event_name="customer.credit_limit_warning").exists()
    customer.credit_limit_base = D("10.5")  # 80% = 8,4: 8 → 8,8 chegaradan o'tadi
    customer.save()
    with django_capture_on_commit_callbacks(execute=True):
        r = seller_client.post(
            URL,
            sale_payload(branch, uzs, cola(products, "1"), [], customer=customer.id),
            format="json",
        )
    assert r.status_code == 201, r.json()
    warning = AuditLog.objects.get(event_name="customer.credit_limit_warning")
    assert warning.payload["percent"] == "83.8"


def test_cancel_credit_sale(
    owner_client, seller_client, branch, uzs, products, stocked, cash, customer
):
    body = sale_payload(
        branch,
        uzs,
        cola(products, "3"),
        [{"method": cash.id, "currency": uzs.id, "amount": "10000"}],
        customer=customer.id,
    )
    sale_id = seller_client.post(URL, body, format="json").json()["id"]
    response = owner_client.post(f"{URL}{sale_id}/cancel/", {"reason": "Qaytardi"}, format="json")
    assert response.status_code == 200, response.json()
    debt = Debt.objects.get()
    assert debt.status == "cancelled"
    last = CustomerLedgerEntry.objects.filter(customer=customer).order_by("-id").first()
    assert (last.type, last.balance_after) == ("cancel", D(0))
    assert payment_services.open_debts_base(customer.id) == 0


def test_cancel_blocked_after_debt_payment(
    owner, owner_client, seller_client, branch, uzs, products, stocked, cash, customer
):
    body = sale_payload(branch, uzs, cola(products, "3"), [], customer=customer.id)
    sale_id = seller_client.post(URL, body, format="json").json()["id"]
    payment_services.receive_debt_payment(
        actor=owner, customer=customer, branch=branch, method=cash, currency=uzs, amount=D("5000")
    )
    response = owner_client.post(f"{URL}{sale_id}/cancel/", {"reason": "x"}, format="json")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "debt_has_payments"
    assert Sale.objects.get(pk=sale_id).status == "completed"


def test_receipt_shows_credit(seller_client, branch, uzs, products, stocked, customer):
    from apps.sales import selectors
    from apps.sales.receipt import build_context

    body = sale_payload(branch, uzs, cola(products, "2"), [], customer=customer.id)
    sale = Sale.objects.get(pk=seller_client.post(URL, body, format="json").json()["id"])
    ctx = build_context(sale, selectors.sale_payments(sale))
    assert ctx["customer"] == "Aliyev Vali"
    assert ctx["debt"] == "20 000"
    assert ctx["due_date"] == sale.due_date.strftime("%d.%m.%Y")


def test_due_date_validation(seller_client, branch, uzs, products, stocked, customer):
    from datetime import timedelta

    from django.utils import timezone

    past = (timezone.localdate() - timedelta(days=1)).isoformat()
    body = sale_payload(branch, uzs, cola(products, "1"), [], customer=customer.id, due_date=past)
    response = seller_client.post(URL, body, format="json")
    assert response.status_code == 400
    assert response.json()["error"]["details"][0]["field"] == "due_date"
    future = (timezone.localdate() + timedelta(days=7)).isoformat()
    ok = seller_client.post(URL, {**body, "due_date": future}, format="json")
    assert ok.status_code == 201 and ok.json()["due_date"] == future
