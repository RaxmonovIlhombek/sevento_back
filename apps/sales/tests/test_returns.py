"""Savdo qaytarish: asl partiyalarga, proporsional summa, qarzdan ayirish, pul qaytarish."""

from decimal import Decimal

import pytest

from apps.inventory.models import Batch, StockLevel, StockMovement
from apps.payments import services as payment_services
from apps.payments.models import Cashbox, Customer, CustomerLedgerEntry, Debt, Payment
from apps.sales.models import Sale, SaleReturn
from core.models import OutboxEvent

from .conftest import sale_payload

pytestmark = pytest.mark.django_db

D = Decimal
SALES = "/api/v1/sales/"
URL = "/api/v1/sales/returns/"


def cola_qty(branch, products):
    return StockLevel.objects.get(branch=branch, product=products["cola"]).quantity


def make_sale(client, branch, uzs, products, qty, payments, **extra):
    body = sale_payload(
        branch,
        uzs,
        [{"product": products["cola"].id, "quantity": qty, **extra.pop("line", {})}],
        payments,
        **extra,
    )
    response = client.post(SALES, body, format="json")
    assert response.status_code == 201, response.json()
    return response.json()


def ret(client, sale, lines, reason="Sifatsiz", **extra):
    return client.post(
        URL,
        {
            "sale": sale["id"],
            "items": [{"sale_item": sale["items"][i]["id"], "quantity": q} for i, q in lines],
            "reason": reason,
            **extra,
        },
        format="json",
    )


def uzs_cash_balance(branch, uzs):
    return Cashbox.objects.get(branch=branch, currency=uzs).balance


def test_partial_return_cash_sale(seller_client, branch, uzs, products, stocked, cash):
    sale = make_sale(
        seller_client,
        branch,
        uzs,
        products,
        "12",
        [{"method": cash.id, "currency": uzs.id, "amount": "120000"}],
    )
    response = ret(seller_client, sale, [(0, "3")])
    assert response.status_code == 201, response.json()
    data = response.json()
    assert data["number"].startswith("Q-TSH1-")
    assert (D(data["total"]), D(data["refund_amount"]), D(data["debt_reduction"])) == (
        D("30000"),
        D("30000"),
        D("0"),
    )
    assert data["refund_method_name"] == "Naqd pul"
    assert data["cost_base"] is None  # sotuvchi tannarxni ko'rmaydi
    # FIFO chiqim: 10×0,60 + 2×0,70; qaytarish oxirgisidan: 2×0,70 + 1×0,60 = 2,00
    sale_return = SaleReturn.objects.get()
    assert sale_return.cost_base == D("2.0000")
    remaining = dict(
        Batch.objects.filter(product=products["cola"]).values_list("pk", "quantity_remaining")
    )
    assert remaining == {stocked["cola1"].pk: D("1"), stocked["cola2"].pk: D("10")}
    assert cola_qty(branch, products) == D("11")
    assert StockMovement.objects.filter(type="sale_return_in").count() == 2
    assert uzs_cash_balance(branch, uzs) == D("90000")
    refund = Payment.objects.get(kind="refund")
    assert refund.document_type == "sale_return" and refund.reversal_of is None

    detail = seller_client.get(f"{SALES}{sale['id']}/").json()
    assert detail["return_state"] == "partial" and D(detail["returned_total"]) == D("30000")
    assert D(detail["items"][0]["returned_quantity"]) == D("3")
    assert detail["can_return"] is True and detail["can_cancel"] is False
    assert [r["number"] for r in detail["returns"]] == [data["number"]]

    rest = ret(seller_client, sale, [(0, "9")])
    assert rest.status_code == 201, rest.json()
    final = seller_client.get(f"{SALES}{sale['id']}/").json()
    assert final["return_state"] == "full" and final["can_return"] is False
    assert cola_qty(branch, products) == D("20")
    assert uzs_cash_balance(branch, uzs) == D("0")
    sale_row = Sale.objects.get(pk=sale["id"])
    assert sale_row.profit_base == 0 and sale_row.returned_cost_base == sale_row.cost_base


def test_discounted_line_returns_sum_to_line_total(
    seller_client, branch, uzs, products, stocked, cash
):
    sale = make_sale(
        seller_client,
        branch,
        uzs,
        products,
        "3",
        [{"method": cash.id, "currency": uzs.id, "amount": "29000"}],
        line={"discount_amount": "1000"},
    )
    amounts = [D(ret(seller_client, sale, [(0, "1")]).json()["total"]) for _ in range(3)]
    assert amounts == [D("9667"), D("9666"), D("9667")]
    assert sum(amounts) == D("29000")


def test_credit_sale_reduces_debt_first(seller_client, branch, uzs, products, stocked, cash):
    customer = Customer.objects.create(name="Aliyev Vali", credit_limit_base=D("100"))
    sale = make_sale(
        seller_client,
        branch,
        uzs,
        products,
        "12",
        [{"method": cash.id, "currency": uzs.id, "amount": "20000"}],
        customer=customer.id,
    )
    first = ret(seller_client, sale, [(0, "5")]).json()
    assert (D(first["debt_reduction"]), D(first["refund_amount"])) == (D("50000"), D("0"))
    debt = Debt.objects.get()
    assert (debt.returned_amount, debt.remaining, debt.status) == (D("50000"), D("50000"), "open")
    entry = CustomerLedgerEntry.objects.filter(customer=customer).latest("id")
    assert (entry.type, entry.amount, entry.balance_after) == ("return", D("-50000"), D("50000"))
    assert entry.document_type == "sale" and entry.document_id == sale["id"]
    assert payment_services.open_debts_base(customer.id) == D("4.0000")
    assert not Payment.objects.filter(kind="refund").exists()

    second = ret(seller_client, sale, [(0, "7")]).json()
    # 70 000: qarz qoldig'i 50 000 yopiladi, 20 000 naqd qaytariladi
    assert (D(second["debt_reduction"]), D(second["refund_amount"])) == (D("50000"), D("20000"))
    debt.refresh_from_db()
    assert (debt.status, debt.remaining) == ("paid", D("0"))
    assert uzs_cash_balance(branch, uzs) == D("0")
    names = set(OutboxEvent.objects.values_list("name", flat=True))
    assert {"debt.reduced", "debt.settled", "sale_return.completed"} <= names


def test_partly_paid_debt(owner, seller_client, branch, uzs, products, stocked, cash):
    customer = Customer.objects.create(name="Karimov", credit_limit_base=D("100"))
    sale = make_sale(seller_client, branch, uzs, products, "10", [], customer=customer.id)
    payment_services.receive_debt_payment(
        actor=owner, customer=customer, branch=branch, method=cash, currency=uzs, amount=D("30000")
    )
    data = ret(seller_client, sale, [(0, "9")]).json()
    # qarz 100 000 − to'langan 30 000 = 70 000 ayiriladi; 90 000 − 70 000 = 20 000 naqd
    assert (D(data["debt_reduction"]), D(data["refund_amount"])) == (D("70000"), D("20000"))
    assert Debt.objects.get().status == "paid"


def test_validation_and_state_rules(
    seller_client, owner_client, branch, uzs, products, stocked, cash
):
    sale = make_sale(
        seller_client,
        branch,
        uzs,
        products,
        "2",
        [{"method": cash.id, "currency": uzs.id, "amount": "20000"}],
    )
    too_many = ret(seller_client, sale, [(0, "3")])
    assert too_many.status_code == 400
    assert too_many.json()["error"]["details"][0] == {
        "field": "items.0.quantity",
        "code": "exceeds_sold",
        "message": "Qaytarish mumkin: 2",
    }
    frac = ret(seller_client, sale, [(0, "0.5")])
    assert frac.json()["error"]["details"][0]["code"] == "unit_precision"
    alien_line = seller_client.post(
        URL,
        {"sale": sale["id"], "items": [{"sale_item": 999999, "quantity": "1"}], "reason": "x"},
        format="json",
    )
    assert alien_line.json()["error"]["details"][0]["code"] == "not_in_sale"

    assert ret(seller_client, sale, [(0, "1")]).status_code == 201
    cancel = owner_client.post(f"{SALES}{sale['id']}/cancel/", {"reason": "x"}, format="json")
    assert cancel.status_code == 409 and cancel.json()["error"]["code"] == "sale_has_returns"

    other = make_sale(
        seller_client,
        branch,
        uzs,
        products,
        "1",
        [{"method": cash.id, "currency": uzs.id, "amount": "10000"}],
    )
    owner_client.post(f"{SALES}{other['id']}/cancel/", {"reason": "x"}, format="json")
    cancelled = ret(seller_client, other, [(0, "1")])
    assert cancelled.status_code == 409
    assert cancelled.json()["error"]["code"] == "invalid_status_transition"


def test_insufficient_cash_rolls_back_then_card(owner_client, branch, uzs, products, stocked, card):
    sale = make_sale(
        owner_client,
        branch,
        uzs,
        products,
        "2",
        [{"method": card.id, "currency": uzs.id, "amount": "20000"}],
    )
    response = ret(owner_client, sale, [(0, "1")])
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "insufficient_cash"
    assert SaleReturn.objects.count() == 0 and cola_qty(branch, products) == D("18")
    by_card = ret(owner_client, sale, [(0, "1")], refund_method=card.id)
    assert by_card.status_code == 201, by_card.json()
    assert by_card.json()["refund_method_name"] == "Plastik karta (terminal)"
    assert cola_qty(branch, products) == D("19")


def test_permissions(
    seller_client, storekeeper, as_user, roles, branch2, branch, uzs, products, stocked, cash
):
    from apps.accounts.models import User, UserBranch

    sale = make_sale(
        seller_client,
        branch,
        uzs,
        products,
        "1",
        [{"method": cash.id, "currency": uzs.id, "amount": "10000"}],
    )
    assert ret(as_user(storekeeper), sale, [(0, "1")]).status_code == 403
    # shu nuqtadagi boshqa sotuvchi — faqat o'z savdosini (sales.cancel siz)
    colleague = User.objects.create_user(
        username="sotuvchi3", password="parol12345", full_name="S3", role=roles["seller"]
    )
    UserBranch.objects.create(user=colleague, branch=branch, is_default=True)
    other = ret(as_user(colleague), sale, [(0, "1")])
    assert other.status_code == 403 and other.json()["error"]["code"] == "return_forbidden"
    assert as_user(colleague).get(f"{SALES}{sale['id']}/").json()["can_return"] is False
    alien = User.objects.create_user(
        username="sotuvchi2", password="parol12345", full_name="S2", role=roles["seller"]
    )
    UserBranch.objects.create(user=alien, branch=branch2, is_default=True)
    response = ret(as_user(alien), sale, [(0, "1")])
    assert response.status_code == 403 and response.json()["error"]["code"] == "branch_forbidden"
    assert as_user(alien).get(URL).json()["count"] == 0


def test_list_summary_and_routes(
    seller_client, owner_client, owner, branch, uzs, products, stocked, cash
):
    from apps.realtime.router import resolve
    from core.events import Event

    sale = make_sale(
        seller_client,
        branch,
        uzs,
        products,
        "12",
        [{"method": cash.id, "currency": uzs.id, "amount": "120000"}],
    )
    data = ret(seller_client, sale, [(0, "2")]).json()
    assert seller_client.get(URL, {"sale": sale["id"]}).json()["count"] == 1
    assert seller_client.get(URL, {"search": sale["number"]}).json()["count"] == 1
    detail = owner_client.get(f"{URL}{data['id']}/").json()
    assert detail["items"][0]["product_name"] == "Cola 1L" and detail["cost_base"] == "1.4000"

    summary = owner_client.get(f"{SALES}summary/").json()
    assert summary["returns_count"] == 1
    # savdo 120 000 so'm = 9,6 USD; qaytarish 1,6 USD; tannarx 6,0+1,4 − 1,4 qaytgan
    assert D(summary["returns_total_base"]) == D("1.6")
    assert D(summary["profit_base"]) == (D("9.6") - D("1.6")) - (D("7.4") - D("1.4"))

    event = Event.from_outbox(OutboxEvent.objects.get(name="sale_return.completed"))
    groups = {o.group: o.message["type"] for o in resolve(event)}
    assert groups[f"branch_{branch.id}"] == "sale_return.completed"
    assert groups[f"user_{owner.id}"] == "dashboard.updated"
