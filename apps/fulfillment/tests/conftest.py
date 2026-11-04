import pytest

from apps.accounts.models import User, UserBranch
from apps.sales.tests.conftest import *  # noqa: F401,F403  (kurs, narx, ombor fixture lari)
from apps.sales.tests.conftest import sale_payload

URL = "/api/v1/fulfillment/orders/"


def make_user(roles, code, username, branches=()):
    user = User.objects.create_user(
        username=username, password="parol12345", full_name=username.title(), role=roles[code]
    )
    for i, b in enumerate(branches):
        UserBranch.objects.create(user=user, branch=b, is_default=(i == 0))
    return user


@pytest.fixture
def operator(roles, branch):
    return make_user(roles, "operator", "operator1", [branch])


@pytest.fixture
def courier(roles, branch):
    return make_user(roles, "courier", "kuryer1", [branch])


@pytest.fixture
def courier2(roles, branch):
    return make_user(roles, "courier", "kuryer2", [branch])


@pytest.fixture
def manager(roles, branch):
    return make_user(roles, "branch_manager", "filial1", [branch])


@pytest.fixture
def other_storekeeper(roles, branch2):
    return make_user(roles, "storekeeper", "omborchi2", [branch2])


@pytest.fixture
def sale(seller_client, branch, uzs, products, stocked, cash):
    body = sale_payload(
        branch,
        uzs,
        [{"product": products["cola"].id, "quantity": "2"}],
        [{"method": cash.id, "currency": uzs.id, "amount": "20000"}],
    )
    response = seller_client.post("/api/v1/sales/", body, format="json")
    assert response.status_code == 201, response.json()
    return response.json()


@pytest.fixture
def order(seller_client, sale):
    response = seller_client.post(
        URL, {"sale": sale["id"], "address": "Samarqand, Registon 1"}, format="json"
    )
    assert response.status_code == 201, response.json()
    return response.json()
