import pytest

from apps.accounts.models import Role, User, UserBranch
from apps.hr.models import Department, Employee, Position
from apps.payments.models import Customer

pytestmark = pytest.mark.django_db

HIRE = "/api/v1/hr/employees/hire/"
CUSTOMERS = "/api/v1/payments/customers/"


@pytest.fixture
def manager(roles, branch2):
    user = User.objects.create_user(
        username="samarqand",
        password="parol12345",
        full_name="Samarqand",
        role=roles["branch_manager"],
    )
    UserBranch.objects.create(user=user, branch=branch2, is_default=True)
    return user


@pytest.fixture
def org(db):
    dep = Department.objects.create(name="Ombor")
    pos = Position.objects.create(name="Omborchi", department=dep)
    return dep, pos


def payload(roles, branch, org, role="storekeeper", username="yangi1", **extra):
    dep, pos = org
    return {
        "full_name": "Yangi Xodim",
        "username": username,
        "password": "kuchli-parol-2026",
        "role": roles[role].id,
        "branch": branch.id,
        "department": dep.id,
        "position": pos.id,
        **extra,
    }


def test_manager_hires_storekeeper_into_own_branch(roles, branch2, manager, org, as_user):
    response = as_user(manager).post(HIRE, payload(roles, branch2, org), format="json")
    assert response.status_code == 201, response.json()
    user = User.objects.get(username="yangi1")
    assert user.role.code == "storekeeper"
    assert user.accessible_branch_ids() == frozenset({branch2.id})
    employee = Employee.objects.get(user=user)
    assert employee.branch_id == branch2.id and employee.employee_number.startswith("E-")
    # yangi xodim faqat o'z nuqtasini ko'radi va kira oladi
    login = as_user(user).get("/api/v1/hr/employees/")
    assert login.status_code == 403  # omborchida HR huquqi yo'q


def test_manager_cannot_hire_into_other_branch_or_higher_role(
    roles, branch, branch2, manager, org, as_user
):
    client = as_user(manager)
    other_branch = client.post(HIRE, payload(roles, branch, org), format="json")
    assert other_branch.status_code == 403
    for role in ("owner", "branch_manager", "hr_manager", "accountant"):
        r = client.post(
            HIRE, payload(roles, branch2, org, role=role, username=f"u-{role}"), format="json"
        )
        assert r.status_code == 403, role
    assert not User.objects.filter(username__startswith="u-").exists()


def test_manager_can_hire_branch_accountant_and_courier_and_operator(
    roles, branch2, manager, org, as_user
):
    client = as_user(manager)
    for role in ("branch_accountant", "courier", "operator", "seller"):
        r = client.post(
            HIRE, payload(roles, branch2, org, role=role, username=f"x-{role}"), format="json"
        )
        assert r.status_code == 201, (role, r.json())
    accountant = User.objects.get(username="x-branch_accountant")
    assert accountant.accessible_branch_ids() == frozenset({branch2.id})  # hamma nuqta emas


def test_owner_hires_branch_manager_anywhere(roles, branch, org, owner_client):
    r = owner_client.post(HIRE, payload(roles, branch, org, role="branch_manager"), format="json")
    assert r.status_code == 201, r.json()
    assert User.objects.get(username="yangi1").role.code == "branch_manager"


def test_seller_cannot_hire(roles, branch, org, seller_client):
    assert seller_client.post(HIRE, payload(roles, branch, org), format="json").status_code == 403


def test_duplicate_username_and_weak_password(roles, branch2, manager, org, as_user, owner):
    client = as_user(manager)
    assert (
        client.post(
            HIRE, payload(roles, branch2, org, username=owner.username), format="json"
        ).status_code
        == 400
    )
    assert (
        client.post(HIRE, payload(roles, branch2, org, password="123"), format="json").status_code
        == 400
    )


def test_manager_terminates_staff_but_not_peers(
    roles, branch2, manager, org, as_user, owner_client
):
    client = as_user(manager)
    client.post(HIRE, payload(roles, branch2, org), format="json")
    staff = Employee.objects.get(user__username="yangi1")
    r = client.post(f"/api/v1/hr/employees/{staff.id}/terminate/", {}, format="json")
    assert r.status_code == 200, r.json()
    staff.refresh_from_db()
    staff.user.refresh_from_db()
    assert staff.status == "terminated" and staff.user.is_active is False
    assert (
        client.post(f"/api/v1/hr/employees/{staff.id}/terminate/", {}, format="json").status_code
        == 409
    )

    # boshqa filial rahbari (teng daraja) — egasi boshqaradi, hamkasb emas
    owner_client.post(
        HIRE, payload(roles, branch2, org, role="branch_manager", username="peer"), format="json"
    )
    peer = Employee.objects.get(user__username="peer")
    assert (
        client.post(f"/api/v1/hr/employees/{peer.id}/terminate/", {}, format="json").status_code
        == 403
    )
    assert (
        owner_client.post(
            f"/api/v1/hr/employees/{peer.id}/terminate/", {}, format="json"
        ).status_code
        == 200
    )


def test_customers_are_scoped_to_branch(roles, branch, branch2, manager, owner_client, as_user):
    Customer.objects.create(name="Toshkent mijozi", primary_branch=branch)
    Customer.objects.create(name="Samarqand mijozi", primary_branch=branch2)
    client = as_user(manager)
    names = [c["name"] for c in client.get(CUSTOMERS).json()["results"]]
    assert names == ["Samarqand mijozi"]
    # yangi mijoz — avtomatik o'z nuqtasiga
    created = client.post(CUSTOMERS, {"name": "Yangi mijoz"}, format="json")
    assert created.status_code == 201, created.json()
    assert Customer.objects.get(name="Yangi mijoz").primary_branch_id == branch2.id
    # begona nuqtaga yozolmaydi
    bad = client.post(CUSTOMERS, {"name": "X", "primary_branch": branch.id}, format="json")
    assert bad.status_code == 403
    # egasi hammasini ko'radi
    all_names = {c["name"] for c in owner_client.get(CUSTOMERS).json()["results"]}
    assert {"Toshkent mijozi", "Samarqand mijozi", "Yangi mijoz"} <= all_names


def test_new_roles_exist_with_right_scope(roles):
    assert "branches.view_all" not in roles["branch_accountant"].capabilities
    assert "branches.view_all" in roles["accountant"].capabilities
    assert roles["operator"].capabilities and "fulfillment.verify" in roles["operator"].capabilities
    assert "fulfillment.pack" in roles["storekeeper"].capabilities
    assert Role.objects.filter(code="operator").exists()
