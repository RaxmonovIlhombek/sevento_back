from decimal import Decimal

import pytest

from apps.accounts.models import User
from apps.notifications.models import Notification
from apps.workflow.models import ApprovalInstance, ApprovalRule

pytestmark = pytest.mark.django_db

INSTANCES = "/api/v1/workflow/instances/"
RULES = "/api/v1/workflow/rules/"


@pytest.fixture
def boss(roles):
    return User.objects.create_user(
        username="boss", password="parol12345", full_name="Boss", role=roles["owner"]
    )


@pytest.fixture
def accountant_user(accountant):
    return accountant


def _rule(approver, *, seq=1, entity_type="expense", lo="0", hi=None, branch=None):
    return ApprovalRule.objects.create(
        entity_type=entity_type,
        min_amount=Decimal(lo),
        max_amount=None if hi is None else Decimal(hi),
        approver=approver,
        sequence=seq,
        branch=branch,
    )


def _create(client, **over):
    body = {"entity_type": "expense", "title": "Ofis uchun suv", "amount": "150000"}
    body.update(over)
    return client.post(INSTANCES, body, format="json")


def test_request_without_matching_rule_is_rejected(seller_client):
    response = _create(seller_client)
    assert response.status_code == 400
    assert not ApprovalInstance.objects.exists()


def test_create_builds_steps_in_order_and_notifies_first_approver(
    seller_client, boss, accountant_user
):
    _rule(accountant_user, seq=1)
    _rule(boss, seq=2)

    response = _create(seller_client)

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending"
    assert [s["approver"] for s in body["steps"]] == [accountant_user.id, boss.id]
    assert body["current_approver_name"] == accountant_user.full_name
    assert body["can_cancel"] is True
    assert Notification.objects.filter(user=accountant_user, source="workflow").count() == 1
    assert not Notification.objects.filter(user=boss).exists()


def test_amount_range_selects_rules(seller_client, boss, accountant_user):
    _rule(accountant_user, lo="0", hi="1000000")
    _rule(boss, lo="1000000.0001")

    small = _create(seller_client, amount="500000").json()
    big = _create(seller_client, amount="5000000", title="Katta xarajat").json()

    assert [s["approver"] for s in small["steps"]] == [accountant_user.id]
    assert [s["approver"] for s in big["steps"]] == [boss.id]


def test_two_step_approval_is_sequential(seller_client, as_user, boss, accountant_user):
    _rule(accountant_user, seq=1)
    _rule(boss, seq=2)
    pk = _create(seller_client).json()["id"]
    boss_client = as_user(boss)
    acc_client = as_user(accountant_user)

    # navbat 1-bosqichda: rahbar hali hal qila olmaydi
    assert boss_client.post(f"{INSTANCES}{pk}/approve/", {}, format="json").status_code == 403

    first = acc_client.post(f"{INSTANCES}{pk}/approve/", {"comment": "ok"}, format="json")
    assert first.status_code == 200
    assert first.json()["status"] == "pending"
    assert first.json()["current_approver_name"] == boss.full_name
    assert Notification.objects.filter(user=boss, source="workflow").exists()

    last = boss_client.post(f"{INSTANCES}{pk}/approve/", {}, format="json")
    assert last.json()["status"] == "approved"
    assert Notification.objects.filter(
        user__username="sotuvchi", title="So'rovingiz tasdiqlandi"
    ).exists()


def test_reject_ends_request_and_requires_turn(seller_client, as_user, accountant_user, boss):
    _rule(accountant_user)
    pk = _create(seller_client).json()["id"]

    # begona foydalanuvchi so'rovni ko'rmaydi ham
    assert as_user(boss).get(f"{INSTANCES}{pk}/").status_code == 200  # boss — workflow.manage
    response = as_user(accountant_user).post(
        f"{INSTANCES}{pk}/reject/", {"comment": "Kerak emas"}, format="json"
    )
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    again = as_user(accountant_user).post(f"{INSTANCES}{pk}/approve/", {}, format="json")
    assert again.status_code == 400


def test_visibility_is_scoped(seller_client, as_user, storekeeper, accountant_user, boss):
    _rule(accountant_user)
    _create(seller_client)

    assert len(as_user(storekeeper).get(INSTANCES).json()["results"]) == 0
    assert len(as_user(accountant_user).get(INSTANCES).json()["results"]) == 1
    assert len(seller_client.get(INSTANCES).json()["results"]) == 1
    assert len(as_user(boss).get(INSTANCES).json()["results"]) == 1


def test_assigned_scope_and_summary(seller_client, as_user, accountant_user, boss):
    _rule(accountant_user, seq=1)
    _rule(boss, seq=2)
    _create(seller_client)
    acc, bs = as_user(accountant_user), as_user(boss)

    assert len(acc.get(INSTANCES, {"scope": "assigned"}).json()["results"]) == 1
    # rahbar ko'ra oladi, lekin navbat hali unda emas
    assert len(bs.get(INSTANCES, {"scope": "assigned"}).json()["results"]) == 0
    assert acc.get(f"{INSTANCES}summary/").json() == {"assigned": 1, "mine_pending": 0}
    assert seller_client.get(f"{INSTANCES}summary/").json() == {
        "assigned": 0,
        "mine_pending": 1,
    }


def test_requester_can_cancel_only_while_pending(seller_client, as_user, accountant_user):
    _rule(accountant_user)
    pk = _create(seller_client).json()["id"]

    response = seller_client.post(f"{INSTANCES}{pk}/cancel/")
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert seller_client.post(f"{INSTANCES}{pk}/cancel/").status_code == 400


def test_other_user_cannot_cancel(seller_client, as_user, accountant_user):
    _rule(accountant_user)
    pk = _create(seller_client).json()["id"]
    # tasdiqlovchi ko'radi, lekin so'rovchi ham, rahbar ham emas
    assert as_user(accountant_user).post(f"{INSTANCES}{pk}/cancel/").status_code == 403


def test_requester_who_is_the_only_approver_is_auto_approved(owner_client, owner):
    _rule(owner)
    body = _create(owner_client).json()
    assert body["status"] == "approved"
    assert body["steps"] == []


def test_rules_are_manager_only(seller_client, owner_client, accountant_user):
    payload = {
        "entity_type": "expense",
        "min_amount": "0",
        "approver": accountant_user.id,
        "sequence": 1,
    }
    assert seller_client.get(RULES).status_code == 403
    assert seller_client.post(RULES, payload, format="json").status_code == 403

    created = owner_client.post(RULES, payload, format="json")
    assert created.status_code == 201
    assert created.json()["type_label"] == "Xarajat"
    assert (
        owner_client.post(RULES, {**payload, "entity_type": "nope"}, format="json").status_code
        == 400
    )
    assert (
        owner_client.post(
            RULES, {**payload, "min_amount": "10", "max_amount": "5"}, format="json"
        ).status_code
        == 400
    )


def test_instances_cannot_be_edited_or_deleted_directly(seller_client, accountant_user):
    _rule(accountant_user)
    pk = _create(seller_client).json()["id"]
    assert seller_client.patch(f"{INSTANCES}{pk}/", {"status": "approved"}).status_code == 405
    assert seller_client.delete(f"{INSTANCES}{pk}/").status_code == 405
