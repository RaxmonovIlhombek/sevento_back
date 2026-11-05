"""sale.completed -> har qanday savdo (do'kondan olib ketilgani ham) avtomatik
omborchiga yuboriladi, qo'lda "yetkazishga yuborish" shart emas.
"""

import pytest

from apps.fulfillment.models import Fulfillment
from apps.sales.tests.conftest import sale_payload

pytestmark = pytest.mark.django_db


def test_sale_auto_creates_pending_fulfillment(
    seller_client, branch, uzs, products, stocked, cash, django_capture_on_commit_callbacks
):
    body = sale_payload(
        branch,
        uzs,
        [{"product": products["cola"].id, "quantity": "1"}],
        [{"method": cash.id, "currency": uzs.id, "amount": "10000"}],
    )
    with django_capture_on_commit_callbacks(execute=True):
        response = seller_client.post("/api/v1/sales/", body, format="json")
    assert response.status_code == 201, response.json()
    sale_id = response.json()["id"]

    f = Fulfillment.objects.get(sale_id=sale_id)
    assert f.status == Fulfillment.Status.PENDING
    assert f.branch_id == branch.id
    assert f.address == ""
    assert f.steps.count() == 1


def test_auto_created_fulfillment_findable_by_sale_filter(
    seller_client,
    owner_client,
    branch,
    uzs,
    products,
    stocked,
    cash,
    django_capture_on_commit_callbacks,
):
    body = sale_payload(
        branch,
        uzs,
        [{"product": products["cola"].id, "quantity": "1"}],
        [{"method": cash.id, "currency": uzs.id, "amount": "10000"}],
    )
    with django_capture_on_commit_callbacks(execute=True):
        response = seller_client.post("/api/v1/sales/", body, format="json")
    sale_id = response.json()["id"]

    resp = owner_client.get("/api/v1/fulfillment/orders/", {"sale": sale_id})
    assert resp.status_code == 200
    assert [r["sale"] for r in resp.data["results"]] == [sale_id]
