"""To'lov turlari, kassa qoldig'i va jurnali: API, ruxsatlar, nuqta chegarasi, qaytim xatosi."""

from decimal import Decimal

import pytest

from apps.currency.models import Currency
from apps.payments import services
from apps.payments.exceptions import InsufficientCash
from apps.payments.models import Cashbox, PaymentMethod
from apps.payments.types import PaymentDoc

pytestmark = pytest.mark.django_db

D = Decimal


@pytest.fixture
def uzs(db):
    return Currency.objects.get(code="UZS")


@pytest.fixture
def usd_rate(owner):
    from apps.currency import services as currency_services

    currency_services.set_rate(
        actor=owner, currency=Currency.objects.get(code="USD"), rate=D("12500")
    )


def test_seeded_methods_and_categories(db):
    assert list(PaymentMethod.objects.values_list("code", "is_cash")) == [
        ("cash", True),
        ("card", False),
        ("transfer", False),
    ]


def test_methods_api_permissions(seller_client, owner_client):
    assert seller_client.get("/api/v1/payments/methods/").status_code == 200
    body = {"code": "Click", "name": "Click", "provider": "manual"}
    assert seller_client.post("/api/v1/payments/methods/", body, format="json").status_code == 403
    response = owner_client.post("/api/v1/payments/methods/", body, format="json")
    assert response.status_code == 201, response.json()
    assert response.json()["code"] == "click"
    dup = owner_client.post("/api/v1/payments/methods/", body, format="json")
    assert dup.status_code == 400
    bad = owner_client.post(
        "/api/v1/payments/methods/",
        {"code": "payme", "name": "Payme", "provider": "payme"},
        format="json",
    )
    assert bad.status_code == 400  # provayder hali ulanmagan


def test_storekeeper_cannot_see_cash(storekeeper, as_user):
    assert as_user(storekeeper).get("/api/v1/payments/cashboxes/").status_code == 403


def test_cashbox_scope_and_journal(
    owner, seller, seller_client, owner_client, branch, branch2, uzs, usd_rate
):
    cash = PaymentMethod.objects.get(code="cash")
    for b, amount in ((branch, "50000"), (branch2, "70000")):
        services.receive_payment(
            actor=owner,
            branch=b,
            method=cash,
            currency=uzs,
            amount=D(amount),
            doc=PaymentDoc(type="sale", id=b.id, number=f"S-{b.code}"),
        )
    seller_boxes = seller_client.get("/api/v1/payments/cashboxes/").json()
    assert [(c["branch"], D(c["balance"])) for c in seller_boxes] == [(branch.id, D("50000"))]
    assert len(owner_client.get("/api/v1/payments/cashboxes/").json()) == 2

    journal = seller_client.get("/api/v1/payments/cash-transactions/").json()["results"]
    assert [(t["direction"], t["category_code"], D(t["amount"])) for t in journal] == [
        ("in", "sale", D("50000"))
    ]
    assert journal[0]["document_number"] == "S-TSH1"
    filtered = owner_client.get(
        "/api/v1/payments/cash-transactions/", {"branch": branch2.id, "direction": "in"}
    ).json()["results"]
    assert len(filtered) == 1


def test_change_without_cash_fails(owner, branch, uzs, usd_rate):
    with pytest.raises(InsufficientCash):
        services.give_change(
            actor=owner,
            branch=branch,
            currency=uzs,
            amount=D("1000"),
            doc=PaymentDoc(type="sale", id=1),
        )
    assert not Cashbox.objects.filter(balance__gt=0).exists()


def test_reverse_returns_change_before_refund(owner, branch, uzs, usd_rate):
    cash = PaymentMethod.objects.get(code="cash")
    doc = PaymentDoc(type="sale", id=7, number="S-7")
    services.receive_payment(
        actor=owner, branch=branch, method=cash, currency=uzs, amount=D("100000"), doc=doc
    )
    services.give_change(actor=owner, branch=branch, currency=uzs, amount=D("5000"), doc=doc)
    box = Cashbox.objects.get(branch=branch, currency=uzs)
    assert box.balance == D("95000")
    mirrors = services.reverse_document_payments(actor=owner, doc=doc, reason="test")
    assert [m.kind for m in mirrors] == ["change_return", "refund"]
    box.refresh_from_db()
    assert box.balance == 0
    # asl kurs saqlanadi — asosiy valyutada aniq teskari
    assert sum(m.amount_base for m in mirrors if m.direction == "in") == D("0.4")
