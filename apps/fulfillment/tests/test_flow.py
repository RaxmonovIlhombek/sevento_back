import pytest

from .conftest import URL

pytestmark = pytest.mark.django_db


def act(client, order, action, **body):
    return client.post(f"{URL}{order['id']}/{action}/", body, format="json")


def ids(client, **params):
    response = client.get(URL, params)
    assert response.status_code == 200, response.json()
    return [row["id"] for row in response.json()["results"]]


def test_full_flow_storekeeper_operator_courier(
    as_user, storekeeper, operator, courier, manager, order
):
    sk, op, co, mgr = (as_user(u) for u in (storekeeper, operator, courier, manager))
    assert order["status"] == "pending"
    assert order["address"] == "Samarqand, Registon 1"

    # omborchi taxlaydi
    assert act(sk, order, "pack").json()["status"] == "packed"
    # kuryer hali ko'rmaydi — operator tekshirmagan
    assert ids(co) == []
    # operator tekshirib "tayyor" qiladi
    assert act(op, order, "verify").json()["status"] == "ready"
    # endi kuryer ko'radi va qabul qiladi
    assert ids(co) == [order["id"]]
    accepted = act(co, order, "accept").json()
    assert accepted["status"] == "on_the_way"
    assert accepted["courier"] == courier.pk
    # "yetib keldim, hammasini berdim"
    done = act(co, order, "deliver", note="Hammasi topshirildi").json()
    assert done["status"] == "delivered"
    assert done["delivered_note"] == "Hammasi topshirildi"

    # rahbar butun jarayonni tarix bilan ko'radi
    detail = mgr.get(f"{URL}{order['id']}/").json()
    assert [s["status"] for s in detail["steps"]] == [
        "pending",
        "packed",
        "ready",
        "on_the_way",
        "delivered",
    ]
    assert detail["items"][0]["product_name"] == "Cola 1L"


def test_visibility_by_role(as_user, storekeeper, operator, courier, manager, order):
    sk, op, co, mgr = (as_user(u) for u in (storekeeper, operator, courier, manager))
    oid = order["id"]
    # yangi buyurtma: faqat omborchi va rahbar; operator va kuryer hali ko'rmaydi (operator
    # fulfillment.view bilan hammasini kuzatadi, shuning uchun uni alohida tekshiramiz)
    assert ids(sk) == [oid] and ids(mgr) == [oid]
    assert ids(co) == []
    act(sk, order, "pack")
    assert ids(op) == [oid]
    assert ids(co) == []


def test_operator_rejects_back_to_storekeeper(as_user, storekeeper, operator, order):
    sk, op = as_user(storekeeper), as_user(operator)
    act(sk, order, "pack")
    assert act(op, order, "reject").status_code == 400  # sabab majburiy
    back = act(op, order, "reject", reason="2 dona kam taxlangan").json()
    assert back["status"] == "pending"
    assert back["reject_reason"] == "2 dona kam taxlangan"
    # omborchi qayta taxlay oladi
    assert act(sk, order, "pack").json()["status"] == "packed"


def test_invalid_transitions_and_wrong_role(
    as_user, owner_client, storekeeper, operator, courier, order
):
    sk, op, co = as_user(storekeeper), as_user(operator), as_user(courier)
    # operator taxlay olmaydi, omborchi tekshira olmaydi, kuryer ish boshlay olmaydi
    assert act(op, order, "pack").status_code == 403
    assert act(sk, order, "verify").status_code == 403
    assert act(co, order, "pack").status_code == 403
    # tartibni buzish: egasi ham pending ni to'g'ridan-to'g'ri yetkazildi qila olmaydi
    assert act(owner_client, order, "accept").status_code == 409
    assert act(owner_client, order, "deliver").status_code == 409


def test_only_one_courier_gets_the_order(as_user, storekeeper, operator, courier, courier2, order):
    act(as_user(storekeeper), order, "pack")
    act(as_user(operator), order, "verify")
    first, second = as_user(courier), as_user(courier2)
    assert act(first, order, "accept").status_code == 200
    assert act(second, order, "accept").status_code in (403, 404, 409)
    # boshqa kuryer yetkaza olmaydi
    assert act(second, order, "deliver").status_code in (403, 404)


def test_other_branch_cannot_touch_order(as_user, other_storekeeper, order):
    client = as_user(other_storekeeper)
    assert ids(client) == []
    assert act(client, order, "pack").status_code == 404
    assert client.get(f"{URL}{order['id']}/").status_code == 404


def test_cancel_only_by_manager(as_user, storekeeper, manager, order):
    assert act(as_user(storekeeper), order, "cancel", reason="x").status_code == 403
    mgr = as_user(manager)
    assert act(mgr, order, "cancel").status_code == 400
    assert act(mgr, order, "cancel", reason="Mijoz rad etdi").json()["status"] == "cancelled"
    assert act(mgr, order, "pack").status_code == 403  # manager taxlay olmaydi


def test_sale_cannot_be_sent_twice(seller_client, sale, order):
    response = seller_client.post(URL, {"sale": sale["id"]}, format="json")
    assert response.status_code == 409


def test_summary_counts(as_user, storekeeper, manager, order):
    act(as_user(storekeeper), order, "pack")
    data = as_user(manager).get(f"{URL}summary/").json()
    assert data["packed"] == 1 and data["pending"] == 0
