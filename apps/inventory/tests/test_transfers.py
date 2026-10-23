"""Ko'chirish: qoralama → jo'natish (FIFO) → qabul (asl tannarx, farq) | bekor; ruxsatlar, WS."""

from decimal import Decimal

import pytest

from apps.inventory.models import Batch, StockMovement, Transfer, WriteOff
from apps.realtime.router import resolve
from core.events import Event
from core.models import OutboxEvent

from .conftest import assert_invariant, qty

pytestmark = pytest.mark.django_db

D = Decimal
URL = "/api/v1/inventory/transfers/"


def payload(branch, branch2, items, **extra):
    return {
        "from_branch": branch.id,
        "to_branch": branch2.id,
        "items": [{"product": p.id, "quantity": q} for p, q in items],
        **extra,
    }


@pytest.fixture
def stocked(branch, goods, stock_in):
    stock_in(branch, goods["cola"], "10", "1")
    stock_in(branch, goods["cola"], "10", "2")
    stock_in(branch, goods["fanta"], "5", "3")


def create(client, branch, branch2, items, **extra):
    response = client.post(URL, payload(branch, branch2, items, **extra), format="json")
    assert response.status_code == 201, response.json()
    return response.json()


def test_full_flow_preserves_cost(
    sk_client, sk2_client, branch, branch2, goods, stocked, storekeeper2
):
    data = create(sk_client, branch, branch2, [(goods["cola"], "15"), (goods["fanta"], "2")])
    assert data["status"] == "draft" and data["number"].startswith("KO-TSH1-")
    assert data["allowed"] == {"edit": True, "send": True, "receive": False, "cancel": True}
    assert qty(branch, goods["cola"]) == D("20")  # qoralama qoldiqqa tegmaydi

    # qabul qiluvchi qoralamani ko'rmaydi
    assert sk2_client.get(URL).json()["count"] == 0
    assert sk2_client.get(f"{URL}{data['id']}/").status_code == 404

    sent = sk_client.post(f"{URL}{data['id']}/send/").json()
    assert sent["status"] == "sent" and sent["sent_at"]
    assert D(sent["total_cost_base"]) == D("26")  # 10×1 + 5×2 + 2×3
    cola_line = next(i for i in sent["items"] if i["product"] == goods["cola"].id)
    assert D(cola_line["unit_cost_base"]) == D("1.333333")
    assert qty(branch, goods["cola"]) == D("5")
    assert StockMovement.objects.filter(type="transfer_out", document_type="transfer").count() == 3

    incoming = sk2_client.get(URL, {"direction": "in"}).json()
    assert incoming["count"] == 1
    assert sk2_client.get(f"{URL}incoming/").json() == {"count": 1}
    detail = sk2_client.get(f"{URL}{data['id']}/").json()
    assert detail["allowed"] == {"edit": False, "send": False, "receive": True, "cancel": False}

    received = sk2_client.post(f"{URL}{data['id']}/receive/", {}, format="json").json()
    assert received["status"] == "received" and received["has_discrepancy"] is False
    assert qty(branch2, goods["cola"]) == D("15") and qty(branch2, goods["fanta"]) == D("2")
    costs = sorted(
        (b.quantity_initial, b.unit_cost_base, b.parent.branch_id)
        for b in Batch.objects.filter(branch=branch2, product=goods["cola"])
    )
    assert costs == [(D("5"), D("2"), branch.id), (D("10"), D("1"), branch.id)]
    for b, p in ((branch, "cola"), (branch, "fanta"), (branch2, "cola"), (branch2, "fanta")):
        assert_invariant(b, goods[p])
    assert sk2_client.get(f"{URL}incoming/").json() == {"count": 0}
    names = list(OutboxEvent.objects.filter(name__startswith="transfer.").values_list("name"))
    assert [n for (n,) in names] == ["transfer.created", "transfer.sent", "transfer.received"]


def test_receive_with_shortage_writes_off_lost_part(
    sk_client, sk2_client, branch, branch2, goods, stocked
):
    data = create(sk_client, branch, branch2, [(goods["cola"], "15"), (goods["fanta"], "2")])
    sent = sk_client.post(f"{URL}{data['id']}/send/").json()
    cola_line = next(i for i in sent["items"] if i["product"] == goods["cola"].id)
    body = {"items": [{"id": cola_line["id"], "quantity_received": "12"}], "note": "3 ta singan"}
    received = sk2_client.post(f"{URL}{data['id']}/receive/", body, format="json").json()
    assert received["has_discrepancy"] is True
    # FIFO: 10×1 + 5×2 jo'natilgan; qabul 12 → 10×1 + 2×2; yo'qolgan 3×2 = 6
    assert D(received["shortage_cost_base"]) == D("6")
    assert received["receive_note"] == "3 ta singan"
    line = next(i for i in received["items"] if i["id"] == cola_line["id"])
    assert D(line["quantity_received"]) == D("12") and D(line["shortage"]) == D("3")
    assert qty(branch2, goods["cola"]) == D("12") and qty(branch2, goods["fanta"]) == D("2")

    write_off = WriteOff.objects.get(transfer_id=data["id"])
    assert write_off.branch_id == branch2.id and write_off.reason.code == "transfer_shortage"
    assert write_off.total_cost_base == D("6") and write_off.number.startswith("HC-SAM1-")
    item = write_off.items.get()
    assert (item.quantity, item.unit_cost_base) == (D("3"), D("2"))
    # tovar yetib kelmagan — qoldiq harakati yo'q
    assert not StockMovement.objects.filter(document_type="write_off").exists()
    assert received["shortage_write_off"] == {"id": write_off.pk, "number": write_off.number}
    assert_invariant(branch2, goods["cola"])


def test_cancel_sent_restores_original_batches(sk_client, branch, branch2, goods, stocked):
    data = create(sk_client, branch, branch2, [(goods["cola"], "15")])
    sk_client.post(f"{URL}{data['id']}/send/")
    response = sk_client.post(
        f"{URL}{data['id']}/cancel/", {"reason": "Mashina yo'q"}, format="json"
    )
    assert response.status_code == 200, response.json()
    assert response.json()["status"] == "cancelled"
    assert qty(branch, goods["cola"]) == D("20")
    remaining = sorted(
        Batch.objects.filter(branch=branch, product=goods["cola"]).values_list(
            "quantity_remaining", flat=True
        )
    )
    assert remaining == [D("10"), D("10")]
    assert StockMovement.objects.filter(type="transfer_cancel").count() == 2
    assert_invariant(branch, goods["cola"])
    again = sk_client.post(f"{URL}{data['id']}/receive/", {}, format="json")
    assert again.status_code == 403  # omborchi qabul qiluvchi nuqtada emas


def test_cancel_draft_and_invalid_transitions(sk_client, owner_client, branch, branch2, goods):
    data = create(sk_client, branch, branch2, [(goods["cola"], "1")])
    assert (
        owner_client.post(f"{URL}{data['id']}/receive/", {}, format="json").json()["error"]["code"]
        == "invalid_status_transition"
    )
    sk_client.post(f"{URL}{data['id']}/cancel/", {"reason": "x"}, format="json")
    response = sk_client.post(f"{URL}{data['id']}/send/")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_status_transition"


def test_insufficient_stock_points_to_line(sk_client, branch, branch2, goods, stocked):
    data = create(sk_client, branch, branch2, [(goods["fanta"], "1"), (goods["cola"], "25")])
    response = sk_client.post(f"{URL}{data['id']}/send/")
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "insufficient_stock"
    assert error["details"][0] == {
        "field": "items.1.quantity",
        "code": "insufficient_stock",
        "message": "Mavjud: 20",
    }
    assert qty(branch, goods["fanta"]) == D("5")  # tranzaksiya to'liq qaytdi
    assert Transfer.objects.get(pk=data["id"]).status == "draft"


def test_validation(sk_client, sk2_client, branch, branch2, goods, stocked):
    same = sk_client.post(URL, payload(branch, branch, [(goods["cola"], "1")]), format="json")
    assert same.status_code == 400
    assert same.json()["error"]["details"][0]["field"] == "to_branch"
    dup = sk_client.post(
        URL, payload(branch, branch2, [(goods["cola"], "1"), (goods["cola"], "2")]), format="json"
    )
    assert dup.json()["error"]["details"][0]["code"] == "duplicate_product"
    frac = sk_client.post(URL, payload(branch, branch2, [(goods["cola"], "1.5")]), format="json")
    assert frac.json()["error"]["details"][0]["code"] == "unit_precision"
    # begona nuqtadan jo'natib bo'lmaydi
    alien = sk2_client.post(URL, payload(branch, branch2, [(goods["cola"], "1")]), format="json")
    assert alien.status_code == 403 and alien.json()["error"]["code"] == "branch_forbidden"

    data = create(sk_client, branch, branch2, [(goods["cola"], "5")])
    sent = sk_client.post(f"{URL}{data['id']}/send/").json()
    line_id = sent["items"][0]["id"]
    over = sk2_client.post(
        f"{URL}{data['id']}/receive/",
        {"items": [{"id": line_id, "quantity_received": "6"}]},
        format="json",
    )
    assert over.status_code == 400
    assert over.json()["error"]["details"][0]["field"] == "items.0.quantity_received"


def test_update_draft(sk_client, branch, branch2, goods, stocked):
    data = create(sk_client, branch, branch2, [(goods["cola"], "1")])
    response = sk_client.patch(
        f"{URL}{data['id']}/",
        {"items": [{"product": goods["fanta"].id, "quantity": "2"}], "note": "Yangi"},
        format="json",
    )
    assert response.status_code == 200, response.json()
    assert response.json()["note"] == "Yangi"
    assert [i["product"] for i in response.json()["items"]] == [goods["fanta"].id]
    sk_client.post(f"{URL}{data['id']}/send/")
    locked = sk_client.patch(f"{URL}{data['id']}/", {"note": "x"}, format="json")
    assert locked.status_code == 409


def test_permissions(seller_client, accountant, as_user, sk2_client, branch, branch2, goods):
    assert seller_client.get(URL).status_code == 403
    acc = as_user(accountant)
    assert acc.get(URL).status_code == 200  # inventory.view_cost — ko'radi
    body = payload(branch, branch2, [(goods["cola"], "1")])
    assert acc.post(URL, body, format="json").status_code == 403


def test_receiver_cannot_cancel(sk_client, sk2_client, branch, branch2, goods, stocked):
    data = create(sk_client, branch, branch2, [(goods["cola"], "1")])
    sk_client.post(f"{URL}{data['id']}/send/")
    response = sk2_client.post(f"{URL}{data['id']}/cancel/", {"reason": "x"}, format="json")
    assert response.status_code == 403


def test_send_is_idempotent(sk_client, branch, branch2, goods, stocked):
    data = create(sk_client, branch, branch2, [(goods["cola"], "3")])
    headers = {"HTTP_IDEMPOTENCY_KEY": "send-1"}
    first = sk_client.post(f"{URL}{data['id']}/send/", **headers)
    second = sk_client.post(f"{URL}{data['id']}/send/", **headers)
    assert first.status_code == second.status_code == 200
    assert qty(branch, goods["cola"]) == D("17")


def _event(name):
    row = OutboxEvent.objects.filter(name=name).latest("id")
    return Event.from_outbox(row)


def test_realtime_routes(owner, sk_client, sk2_client, branch, branch2, goods, stocked):
    data = create(sk_client, branch, branch2, [(goods["cola"], "5")])
    sent = sk_client.post(f"{URL}{data['id']}/send/").json()
    out = resolve(_event("transfer.sent"))
    assert {o.group for o in out} == {f"branch_{branch.id}", f"branch_{branch2.id}"}
    assert len({o.message["id"] for o in out}) == 1  # bitta xabar — takrorsiz
    message = out[0].message
    assert message["type"] == "transfer.sent"
    assert message["payload"]["to_branch_name"] == "Samarqand 1"
    assert "total_cost_base" not in message["payload"]  # sotuvchi ham guruhda — tannarxsiz

    body = {"items": [{"id": sent["items"][0]["id"], "quantity_received": "4"}]}
    sk2_client.post(f"{URL}{data['id']}/receive/", body, format="json")
    groups = {o.group for o in resolve(_event("transfer.received"))}
    assert f"user_{owner.id}" in groups  # farq — rahbarga ham
    payload_ = resolve(_event("transfer.received"))[0].message["payload"]
    assert payload_["has_discrepancy"] is True
    assert payload_["discrepancies"] == [
        {"product_name": "Coca-Cola 1L", "quantity": "5.000", "quantity_received": "4.000"}
    ]

    draft = create(sk_client, branch, branch2, [(goods["cola"], "1")])
    sk_client.post(f"{URL}{draft['id']}/cancel/", {"reason": "x"}, format="json")
    assert {o.group for o in resolve(_event("transfer.cancelled"))} == {f"branch_{branch.id}"}


def test_destinations_lists_all_active_branches(sk_client, seller_client, branch, branch2):
    rows = sk_client.get(f"{URL}destinations/").json()
    assert {r["code"] for r in rows} == {"TSH1", "SAM1"}  # omborchi faqat TSH1 da
    assert seller_client.get(f"{URL}destinations/").status_code == 403
