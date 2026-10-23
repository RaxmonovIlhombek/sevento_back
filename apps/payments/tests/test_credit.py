"""Mijozlar, qarz to'lovi (FIFO, aralash valyuta), qaytarish, muddati o'tgan qarzlar, smena,
qo'lda kassa yozuvi, realtime marshrutlari."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.currency import services as currency_services
from apps.currency.models import Currency
from apps.payments import services
from apps.payments.events import CashEntryCreated, DebtOverdue
from apps.payments.models import (
    Cashbox,
    CashShift,
    CashTransaction,
    Customer,
    CustomerLedgerEntry,
    Debt,
    Payment,
    PaymentMethod,
)
from apps.payments.types import PaymentDoc
from apps.realtime.router import resolve
from core import settings_service

pytestmark = pytest.mark.django_db

D = Decimal
CUSTOMERS = "/api/v1/payments/customers/"


@pytest.fixture
def uzs(db):
    return Currency.objects.get(code="UZS")


@pytest.fixture
def usd(db):
    return Currency.objects.get(code="USD")


@pytest.fixture
def rate(owner, usd):
    currency_services.set_rate(actor=owner, currency=usd, rate=D("12500"))


@pytest.fixture
def cash(db):
    return PaymentMethod.objects.get(code="cash")


@pytest.fixture
def card(db):
    return PaymentMethod.objects.get(code="card")


@pytest.fixture
def customer(db):
    return Customer.objects.create(
        name="Karimov Anvar", phone="+998935554433", credit_limit_base=D("1000")
    )


def debt(owner, customer, branch, currency, amount, days=30, doc_id=1):
    d = services.register_debt(
        actor=owner,
        customer=customer,
        branch=branch,
        currency=currency,
        amount=D(amount),
        doc=PaymentDoc(type="sale", id=doc_id, number=f"S-{doc_id}"),
        due_date=timezone.localdate() + timedelta(days=days),
    )
    return d


# --- mijozlar ---


def test_customer_api_and_credit_limit_permission(seller_client, as_user, accountant):
    body = {"name": "Yangi mijoz", "phone": "+998901234567"}
    response = seller_client.post(CUSTOMERS, body, format="json")
    assert response.status_code == 201, response.json()
    data = response.json()
    assert data["credit"]["limit_base"] == "0.0000"  # sozlama defaulti
    assert data["credit"]["due_days"] == 30
    forbidden = seller_client.patch(
        f"{CUSTOMERS}{data['id']}/", {"credit_limit_base": "500"}, format="json"
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "credit_limit_forbidden"
    ok = as_user(accountant).patch(
        f"{CUSTOMERS}{data['id']}/", {"credit_limit_base": "500"}, format="json"
    )
    assert ok.status_code == 200, ok.json()
    assert ok.json()["credit"]["available_base"] == "500.0000"
    # ism o'zgarishi limitga tegmaydi — sotuvchi qila oladi
    renamed = seller_client.patch(f"{CUSTOMERS}{data['id']}/", {"name": "Mijoz 2"}, format="json")
    assert renamed.status_code == 200


def test_customer_list_balances_and_filters(owner, owner_client, customer, branch, uzs, usd, rate):
    debt(owner, customer, branch, uzs, "125000", days=-3, doc_id=1)  # muddati o'tgan
    debt(owner, customer, branch, usd, "5", doc_id=2)
    Customer.objects.create(name="Qarzsiz mijoz")
    rows = owner_client.get(CUSTOMERS, {"has_debt": "true"}).json()["results"]
    assert [r["name"] for r in rows] == ["Karimov Anvar"]
    row = rows[0]
    assert {b["currency"]: D(b["amount"]) for b in row["balances"]} == {
        "UZS": D("125000"),
        "USD": D("5"),
    }
    assert row["debt_base"] == "15.0000"  # 10 + 5 USD (satr — float emas)
    assert row["effective_credit_limit"] == "1000.0000"
    assert row["has_overdue"] is True
    assert owner_client.get(CUSTOMERS, {"overdue": "true"}).json()["count"] == 1
    assert owner_client.get(CUSTOMERS, {"search": "5554"}).json()["count"] == 1
    detail = owner_client.get(f"{CUSTOMERS}{customer.id}/").json()
    assert D(detail["credit"]["used_base"]) == D("15")
    assert len(detail["open_debts"]) == 2 and detail["open_debts"][0]["is_overdue"] is True


# --- qarz to'lovi ---


def test_debt_payment_fifo_mixed_currency(
    owner, owner_client, customer, branch, uzs, usd, rate, cash, django_capture_on_commit_callbacks
):
    older = debt(owner, customer, branch, uzs, "100000", days=5, doc_id=1)
    newer = debt(owner, customer, branch, usd, "10", days=20, doc_id=2)
    body = {"branch": branch.id, "method": cash.id, "currency": uzs.id, "amount": "150000"}
    with django_capture_on_commit_callbacks(execute=True):
        response = owner_client.post(f"{CUSTOMERS}{customer.id}/pay/", body, format="json")
    assert response.status_code == 201, response.json()
    data = response.json()
    assert [(a["debt"], D(a["amount"]), D(a["payment_amount"])) for a in data["allocations"]] == [
        (older.id, D("100000"), D("100000")),
        (newer.id, D("4"), D("50000")),  # 50 000 / 12 500
    ]
    older.refresh_from_db()
    newer.refresh_from_db()
    assert older.status == "paid" and older.settled_at is not None
    assert newer.status == "open" and newer.remaining == D("6")
    assert Cashbox.objects.get(branch=branch, currency=uzs).balance == D("150000")
    tx = CashTransaction.objects.get()
    assert tx.category.code == "debt_payment" and tx.document_type == "customer"
    balances = {
        e.currency.code: e.balance_after
        for e in CustomerLedgerEntry.objects.filter(customer=customer).order_by("id")
    }
    assert balances == {"UZS": D(0), "USD": D("6")}
    assert AuditLog.objects.filter(event_name="debt.settled", aggregate_id=older.id).exists()
    received = AuditLog.objects.get(event_name="payment.received")
    assert received.payload["customer_id"] == customer.id
    assert len(received.payload["allocated"]) == 2


def test_payment_exceeding_debt_rejected(
    owner, owner_client, customer, branch, uzs, usd, rate, cash
):
    debt(owner, customer, branch, usd, "2")
    body = {"branch": branch.id, "method": cash.id, "currency": uzs.id, "amount": "30000"}
    response = owner_client.post(f"{CUSTOMERS}{customer.id}/pay/", body, format="json")
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "payment_exceeds_debt"
    assert error["details"][0]["message"] == "25000"
    assert Payment.objects.count() == 0


def test_payoff_amount(owner, owner_client, customer, branch, uzs, usd, cash):
    currency_services.set_rate(actor=owner, currency=usd, rate=D("12650.45"))
    debt(owner, customer, branch, usd, "7.5", doc_id=1)
    debt(owner, customer, branch, usd, "7.5", doc_id=2)
    debt(owner, customer, branch, uzs, "1000", doc_id=3)
    data = owner_client.get(f"{CUSTOMERS}{customer.id}/payoff/", {"currency": "UZS"}).json()
    # 2 × 94 878,375 + 1 000 = 190 756,75 → 190 757
    assert data == {"currency": "UZS", "amount": "190757.0000"}
    services.receive_debt_payment(
        actor=owner,
        customer=customer,
        branch=branch,
        method=cash,
        currency=uzs,
        amount=D(data["amount"]),
    )
    assert not Debt.objects.filter(status="open").exists()
    usd_payoff = owner_client.get(f"{CUSTOMERS}{customer.id}/payoff/", {"currency": "USD"}).json()
    assert usd_payoff["amount"] == "0.0000"


def test_rounding_dust_accepted(owner, customer, branch, uzs, usd, cash):
    currency_services.set_rate(actor=owner, currency=usd, rate=D("12650.45"))
    d = debt(owner, customer, branch, usd, "7.5")
    # 7,5 × 12 650,45 = 94 878,375 → kassir 94 879 so'm oladi
    services.receive_debt_payment(
        actor=owner, customer=customer, branch=branch, method=cash, currency=uzs, amount=D("94879")
    )
    d.refresh_from_db()
    assert d.status == "paid"


def test_specific_debt_and_no_debts(owner, owner_client, customer, branch, uzs, rate, cash):
    first = debt(owner, customer, branch, uzs, "10000", days=1, doc_id=1)
    second = debt(owner, customer, branch, uzs, "20000", days=9, doc_id=2)
    body = {
        "branch": branch.id,
        "method": cash.id,
        "currency": uzs.id,
        "amount": "20000",
        "debt_ids": [second.id],
    }
    assert (
        owner_client.post(f"{CUSTOMERS}{customer.id}/pay/", body, format="json").status_code == 201
    )
    first.refresh_from_db()
    second.refresh_from_db()
    assert (first.status, second.status) == ("open", "paid")
    other = Customer.objects.create(name="Qarzsiz")
    response = owner_client.post(
        f"{CUSTOMERS}{other.id}/pay/", {**body, "debt_ids": []}, format="json"
    )
    assert response.status_code == 409 and response.json()["error"]["code"] == "no_open_debts"


def test_pay_idempotent_and_branch_scope(
    seller_client, owner, customer, branch, branch2, uzs, rate, cash
):
    debt(owner, customer, branch, uzs, "50000")
    body = {"branch": branch.id, "method": cash.id, "currency": uzs.id, "amount": "10000"}
    url = f"{CUSTOMERS}{customer.id}/pay/"
    first = seller_client.post(url, body, format="json", HTTP_IDEMPOTENCY_KEY="pay-1")
    second = seller_client.post(url, body, format="json", HTTP_IDEMPOTENCY_KEY="pay-1")
    assert first.status_code == second.status_code == 201
    assert Payment.objects.count() == 1
    other_branch = seller_client.post(url, {**body, "branch": branch2.id}, format="json")
    assert other_branch.status_code == 403


def test_refund_debt_payment(owner, owner_client, seller_client, customer, branch, uzs, rate, cash):
    d = debt(owner, customer, branch, uzs, "50000")
    payment = services.receive_debt_payment(
        actor=owner, customer=customer, branch=branch, method=cash, currency=uzs, amount=D("50000")
    )
    url = f"/api/v1/payments/payments/{payment.id}/refund/"
    assert seller_client.post(url, {"reason": "x"}, format="json").status_code == 403
    response = owner_client.post(url, {"reason": "Xato kiritildi"}, format="json")
    assert response.status_code == 200, response.json()
    assert response.json()["status"] == "reversed"
    d.refresh_from_db()
    assert (d.status, d.paid_amount, d.settled_at) == ("open", 0, None)
    assert Cashbox.objects.get(branch=branch, currency=uzs).balance == 0
    last = CustomerLedgerEntry.objects.filter(customer=customer).order_by("-id").first()
    assert (last.type, last.balance_after) == ("refund", D("50000"))
    again = owner_client.post(url, {"reason": "x"}, format="json")
    assert again.status_code == 409 and again.json()["error"]["code"] == "refund_not_allowed"


def test_payments_journal_and_debts_list(
    owner, seller_client, as_user, roles, customer, branch, branch2, uzs, rate, cash
):
    debt(owner, customer, branch, uzs, "10000", doc_id=1)
    debt(owner, customer, branch2, uzs, "20000", doc_id=2)
    services.receive_debt_payment(
        actor=owner, customer=customer, branch=branch, method=cash, currency=uzs, amount=D("10000")
    )
    debts = seller_client.get("/api/v1/payments/debts/").json()["results"]
    assert [d["branch"] for d in debts] == [branch.id]  # boshqa nuqta qarzi ko'rinmaydi
    payments = seller_client.get("/api/v1/payments/payments/").json()["results"]
    assert [(p["kind"], p["customer_name"]) for p in payments] == [("payment", "Karimov Anvar")]
    open_only = as_user(owner).get("/api/v1/payments/debts/", {"status": "open"}).json()
    assert open_only["count"] == 1


# --- muddati o'tgan qarzlar ---


def test_detect_overdue_once(
    owner, accountant, seller, customer, branch, uzs, rate, django_capture_on_commit_callbacks
):
    late = debt(owner, customer, branch, uzs, "30000", days=-2)
    debt(owner, customer, branch, uzs, "10000", days=3, doc_id=2)
    with django_capture_on_commit_callbacks(execute=True):
        assert services.detect_overdue_debts() == 1
    assert services.detect_overdue_debts() == 0
    log = AuditLog.objects.get(event_name="debt.overdue")
    assert log.aggregate_id == late.id and log.payload["days_overdue"] == 2
    # realtime: buxgalter va rahbarga, sotuvchiga emas
    event = DebtOverdue(
        branch_id=branch.id,
        debt_id=late.id,
        customer_id=customer.id,
        customer_name=customer.name,
        amount_remaining=D("30000"),
        currency="UZS",
        due_date=late.due_date,
        days_overdue=2,
    )
    groups = {o.group for o in resolve(event)}
    assert {f"user_{owner.id}", f"user_{accountant.id}"} <= groups
    assert f"user_{seller.id}" not in groups


def test_celery_task_registered():
    from apps.payments.tasks import detect_overdue_debts
    from core.scheduling import all_periodic_tasks

    assert detect_overdue_debts.name == "payments.detect_overdue_debts"
    assert any(t.task == "payments.detect_overdue_debts" for t in all_periodic_tasks())


# --- smena va qo'lda yozuv ---


def test_shift_open_close_with_difference(
    owner, owner_client, as_user, seller, branch, uzs, usd, rate, cash
):
    services.receive_payment(
        actor=owner,
        branch=branch,
        method=cash,
        currency=uzs,
        amount=D("100000"),
        doc=PaymentDoc(type="sale", id=1, number="S-1"),
    )
    assert (
        as_user(seller)
        .post("/api/v1/payments/shifts/open/", {"branch": branch.id}, format="json")
        .status_code
        == 403
    )
    opened = owner_client.post(
        "/api/v1/payments/shifts/open/", {"branch": branch.id}, format="json"
    )
    assert opened.status_code == 201, opened.json()
    shift = opened.json()
    assert {b["currency_code"]: D(b["opening_balance"]) for b in shift["balances"]} == {
        "UZS": D("100000"),
        "USD": D(0),
    }
    dup = owner_client.post("/api/v1/payments/shifts/open/", {"branch": branch.id}, format="json")
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "shift_already_open"
    services.receive_payment(
        actor=owner,
        branch=branch,
        method=cash,
        currency=uzs,
        amount=D("50000"),
        doc=PaymentDoc(type="sale", id=2, number="S-2"),
    )
    assert CashTransaction.objects.filter(shift_id=shift["id"]).count() == 1
    current = owner_client.get("/api/v1/payments/shifts/current/", {"branch": branch.id}).json()
    assert current["shift"]["id"] == shift["id"]
    # sanaldi: 148 000 (2 000 kam)
    closed = owner_client.post(
        f"/api/v1/payments/shifts/{shift['id']}/close/",
        {"actual": [{"currency": uzs.id, "amount": "148000"}]},
        format="json",
    )
    assert closed.status_code == 200, closed.json()
    row = next(b for b in closed.json()["balances"] if b["currency_code"] == "UZS")
    assert (D(row["expected_balance"]), D(row["actual_balance"]), D(row["difference"])) == (
        D("150000"),
        D("148000"),
        D("-2000"),
    )
    assert Cashbox.objects.get(branch=branch, currency=uzs).balance == D("148000")
    adj = CashTransaction.objects.get(category__code="adjustment")
    assert adj.direction == "out" and adj.amount == D("2000")
    assert (
        owner_client.get("/api/v1/payments/shifts/current/", {"branch": branch.id}).json()["shift"]
        is None
    )


def test_require_open_shift_setting(
    owner, branch, uzs, rate, cash, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        settings_service.set(key="cashbox.require_open_shift", value=True, actor=owner)
    doc = PaymentDoc(type="sale", id=1)
    from apps.payments.exceptions import ShiftClosed

    with pytest.raises(ShiftClosed):
        services.receive_payment(
            actor=owner, branch=branch, method=cash, currency=uzs, amount=D("1"), doc=doc
        )
    services.open_shift(actor=owner, branch=branch)
    services.receive_payment(
        actor=owner, branch=branch, method=cash, currency=uzs, amount=D("1"), doc=doc
    )
    assert CashShift.objects.get().transactions.count() == 1


def test_manual_cash_entries(owner_client, seller_client, branch, uzs):
    url = "/api/v1/payments/cash-transactions/"
    body = {
        "branch": branch.id,
        "currency": uzs.id,
        "direction": "in",
        "category": "deposit",
        "amount": "500000",
        "note": "Boshlang'ich naqd",
    }
    assert seller_client.post(url, body, format="json").status_code == 403
    response = owner_client.post(url, body, format="json")
    assert response.status_code == 201, response.json()
    assert response.json()["category_code"] == "deposit"
    too_much = owner_client.post(
        url,
        {**body, "direction": "out", "category": "withdrawal", "amount": "600000"},
        format="json",
    )
    assert too_much.status_code == 409 and too_much.json()["error"]["code"] == "insufficient_cash"
    wrong_dir = owner_client.post(url, {**body, "direction": "out"}, format="json")
    assert (
        wrong_dir.status_code == 400 and wrong_dir.json()["error"]["code"] == "category_not_manual"
    )
    system = owner_client.post(url, {**body, "category": "sale"}, format="json")
    assert system.status_code == 400  # tizim turi qo'lda tanlanmaydi
    expense = owner_client.post(
        url,
        {**body, "direction": "out", "category": "expense", "amount": "45000", "note": "Ijara"},
        format="json",
    )
    assert expense.status_code == 201
    assert Cashbox.objects.get(branch=branch, currency=uzs).balance == D("455000")
    categories = owner_client.get("/api/v1/payments/cash-categories/").json()
    assert {c["code"] for c in categories if c["is_manual"]} == {"deposit", "withdrawal", "expense"}


def test_cash_updated_route(branch):
    event = CashEntryCreated(
        branch_id=branch.id,
        transaction_id=1,
        cashbox_id=1,
        currency="UZS",
        direction="in",
        category="deposit",
        amount=D("1"),
        note="",
    )
    [out] = resolve(event)
    assert out.group == f"branch_{branch.id}"
    assert out.message["type"] == "cash.updated"
    assert out.message["payload"] == {"branch_id": branch.id, "reason": "manual_entry"}
