"""PayrollRun CRUD va calculate/pay amallari uchun testlar."""

import datetime as dt

import pytest
from rest_framework import status

from apps.hr.models import Department, Employee, Position
from apps.payroll.models import PayrollRun, Payslip


@pytest.fixture
def department(branch) -> Department:
    return Department.objects.create(name="Savdo", branch=branch)


@pytest.fixture
def position(department) -> Position:
    return Position.objects.create(name="Sotuvchi", department=department)


@pytest.fixture
def employee(branch, department, position, roles):
    from apps.accounts.models import User, UserBranch

    user = User.objects.create_user(
        username="xodim1",
        password="parol12345",
        full_name="Xodim Bir",
        role=roles["seller"],
    )
    UserBranch.objects.create(user=user, branch=branch, is_default=True)
    return Employee.objects.create(
        user=user,
        employee_number="EMP-0001",
        department=department,
        position=position,
        branch=branch,
        hire_date=dt.date(2026, 1, 1),
        base_salary=5_000_000,
    )


@pytest.fixture
def run(branch, owner) -> PayrollRun:
    return PayrollRun.objects.create(
        period_start=dt.date(2026, 10, 1),
        period_end=dt.date(2026, 10, 31),
        branch=branch,
        created_by=owner,
    )


@pytest.mark.django_db
def test_create_payroll_run(owner_client, branch):
    resp = owner_client.post(
        "/api/v1/payroll/runs/",
        {"period_start": "2026-11-01", "period_end": "2026-11-30", "branch": branch.id},
        format="json",
    )
    assert resp.status_code == status.HTTP_201_CREATED
    assert resp.data["status"] == PayrollRun.Status.DRAFT
    assert PayrollRun.objects.count() == 1


@pytest.mark.django_db
def test_calculate_creates_payslips_and_updates_totals(owner_client, run, employee):
    resp = owner_client.post(f"/api/v1/payroll/runs/{run.id}/calculate/")
    assert resp.status_code == status.HTTP_200_OK
    run.refresh_from_db()
    assert run.status == PayrollRun.Status.CALCULATED
    assert run.total_gross == employee.base_salary
    assert run.total_net == employee.base_salary
    assert Payslip.objects.filter(run=run, employee=employee).count() == 1


@pytest.mark.django_db
def test_calculate_rejects_non_draft_run(owner_client, run):
    run.status = PayrollRun.Status.CALCULATED
    run.save(update_fields=["status"])
    resp = owner_client.post(f"/api/v1/payroll/runs/{run.id}/calculate/")
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert "Faqat qoralamani" in resp.data["detail"]


@pytest.mark.django_db
def test_pay_requires_calculated_status(owner_client, run):
    resp = owner_client.post(f"/api/v1/payroll/runs/{run.id}/pay/")
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert "Avval hisoblash" in resp.data["detail"]


@pytest.mark.django_db
def test_pay_marks_run_as_paid(owner_client, run):
    run.status = PayrollRun.Status.CALCULATED
    run.save(update_fields=["status"])
    resp = owner_client.post(f"/api/v1/payroll/runs/{run.id}/pay/")
    assert resp.status_code == status.HTTP_200_OK
    run.refresh_from_db()
    assert run.status == PayrollRun.Status.PAID
    assert run.paid_at is not None


@pytest.mark.django_db
def test_seller_cannot_manage_payroll(seller_client, branch):
    resp = seller_client.post(
        "/api/v1/payroll/runs/",
        {"period_start": "2026-11-01", "period_end": "2026-11-30", "branch": branch.id},
        format="json",
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN
