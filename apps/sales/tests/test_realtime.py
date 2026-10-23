"""Savdo hodisalari WebSocket marshrutlari: dashboard.updated — dashboard huquqi borlarga,
stock.changed va payment.received — nuqta guruhiga (tannarxsiz)."""

from decimal import Decimal

import pytest

from apps.payments.events import PaymentReceived
from apps.realtime.router import resolve
from apps.sales.events import SaleCompleted

pytestmark = pytest.mark.django_db


def test_dashboard_updated_goes_to_dashboard_viewers(owner, accountant, seller, branch):
    event = SaleCompleted(
        branch_id=branch.id,
        sale_id=1,
        number="S-TSH1-26-000001",
        seller_id=seller.id,
        currency="UZS",
        total=Decimal("142500"),
        total_base=Decimal("11.4"),
        cost_base=Decimal("8.6"),
        discount_total=Decimal(0),
        items_count=2,
    )
    out = resolve(event)
    groups = {o.group for o in out}
    assert {f"user_{owner.id}", f"user_{accountant.id}"} <= groups
    assert f"user_{seller.id}" not in groups
    message = out[0].message
    assert message["type"] == "dashboard.updated"
    assert message["payload"] == {"branch_id": branch.id, "reason": "sale.completed"}


def test_payment_received_to_branch_group(branch):
    event = PaymentReceived(
        branch_id=branch.id,
        payment_id=5,
        number="T-TSH1-26-000001",
        method="cash",
        currency="UZS",
        amount=Decimal("150000"),
        amount_base=Decimal("12"),
        is_cash=True,
        cashbox_id=3,
        document_type="sale",
        document_id=1,
        document_number="S-1",
    )
    [out] = resolve(event)
    assert out.group == f"branch_{branch.id}"
    assert out.message["payload"]["cashbox_id"] == 3
    assert "amount_base" not in out.message["payload"]


def test_sale_emits_stock_changed_per_line(
    seller_client, branch, uzs, products, stocked, cash, django_capture_on_commit_callbacks
):
    from unittest import mock

    from .conftest import sale_payload

    body = sale_payload(
        branch,
        uzs,
        [
            {"product": products["cola"].id, "quantity": "2"},
            {"product": products["sugar"].id, "quantity": "1"},
        ],
        [{"method": cash.id, "currency": uzs.id, "amount": "35000"}],
    )
    with mock.patch("apps.realtime.router.send_to_groups") as send:
        with django_capture_on_commit_callbacks(execute=True):
            assert seller_client.post("/api/v1/sales/", body, format="json").status_code == 201
    sent = [(c.args[0][0], c.args[1]["type"]) for c in send.call_args_list]
    stock = [g for g, t in sent if t == "stock.changed"]
    assert stock == [f"branch_{branch.id}", f"branch_{branch.id}"]
    assert "dashboard.updated" in {t for _, t in sent}
    for call in send.call_args_list:
        if call.args[1]["type"] == "stock.changed":
            assert "unit_cost_base" not in call.args[1]["payload"]
