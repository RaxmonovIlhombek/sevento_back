from datetime import date

import pytest

from apps.accounts.models import User, UserBranch
from apps.hr.models import Department, Employee, Position

pytestmark = pytest.mark.django_db


def _employee(roles, branch, username, number):
    user = User.objects.create_user(
        username=username, password="parol12345", full_name=username.title(), role=roles["seller"]
    )
    dep, _ = Department.objects.get_or_create(name="Savdo")
    pos, _ = Position.objects.get_or_create(name="Sotuvchi", department=dep)
    return Employee.objects.create(
        user=user,
        employee_number=number,
        department=dep,
        position=pos,
        branch=branch,
        hire_date=date(2026, 1, 1),
    )


@pytest.fixture
def hr_user(roles, branch, branch2):
    user = User.objects.create_user(
        username="kadr", password="parol12345", full_name="Kadr", role=roles["hr_manager"]
    )
    return user


@pytest.fixture
def branch_manager(roles, branch2):
    user = User.objects.create_user(
        username="filial", password="parol12345", full_name="Filial", role=roles["branch_manager"]
    )
    UserBranch.objects.create(user=user, branch=branch2, is_default=True)
    return user


def test_seller_cannot_see_hr(seller_client):
    assert seller_client.get("/api/v1/hr/employees/").status_code == 403
    assert seller_client.get("/api/v1/hr/departments/").status_code == 403


def test_courier_has_no_hr_or_payroll(roles, as_user):
    courier = User.objects.create_user(
        username="kuryer", password="parol12345", full_name="Kuryer", role=roles["courier"]
    )
    client = as_user(courier)
    assert client.get("/api/v1/hr/employees/").status_code == 403
    assert client.get("/api/v1/payroll/runs/").status_code == 403
    assert client.get("/api/v1/accounting/accounts/").status_code == 403


def test_hr_manager_sees_all_branches(roles, branch, branch2, hr_user, as_user):
    _employee(roles, branch, "a1", "E-1")
    _employee(roles, branch2, "a2", "E-2")
    response = as_user(hr_user).get("/api/v1/hr/employees/")
    assert response.status_code == 200
    assert response.json()["count"] == 2


def test_branch_manager_sees_only_own_branch_employees(
    roles, branch, branch2, branch_manager, as_user
):
    _employee(roles, branch, "t1", "E-1")
    _employee(roles, branch2, "s1", "E-2")
    response = as_user(branch_manager).get("/api/v1/hr/employees/")
    assert response.status_code == 200
    numbers = [row["employee_number"] for row in response.json()["results"]]
    assert numbers == ["E-2"]


def test_branch_manager_cannot_edit_hr(branch_manager, as_user):
    response = as_user(branch_manager).post("/api/v1/hr/departments/", {"name": "Yangi"})
    assert response.status_code == 403


def test_owner_has_new_capabilities(owner_client):
    assert owner_client.get("/api/v1/hr/employees/").status_code == 200
    assert owner_client.get("/api/v1/crm/leads/").status_code == 200
    assert owner_client.get("/api/v1/manufacturing/boms/").status_code == 200
