from django.db import transaction
from django.utils import timezone

from apps.accounts import services as account_services
from apps.accounts.capabilities import assignable_role_codes
from core.exceptions import BusinessRuleError

from .models import Employee


def check_branch_allowed(actor, branch_id: int) -> None:
    ids = actor.accessible_branch_ids()
    if ids is not None and branch_id not in ids:
        raise BusinessRuleError(
            "Bu nuqta uchun ruxsat yo'q", code="branch_forbidden", status_code=403
        )


def check_role_allowed(actor, role) -> None:
    """Filial rahbari faqat quyi rollarga yollaydi; egasi — istalgan rolga."""
    allowed = assignable_role_codes(actor)
    if allowed is not None and (role is None or role.code not in allowed):
        raise BusinessRuleError(
            "Bu rolga xodim biriktirishga ruxsat yo'q", code="role_forbidden", status_code=403
        )


def check_manageable(actor, employee: Employee) -> None:
    """Rahbar o'zidan yuqori yoki teng rolli (masalan boshqa filial rahbari) xodimga tegmaydi."""
    if employee.user_id == actor.pk:
        raise BusinessRuleError(
            "O'zingizni o'zgartira olmaysiz", code="self_forbidden", status_code=403
        )
    check_role_allowed(actor, employee.user.role)
    check_branch_allowed(actor, employee.branch_id)


def hire_employee(
    *,
    actor,
    full_name: str,
    username: str,
    password: str,
    role,
    branch,
    department,
    position,
    phone: str = "",
    employee_number: str = "",
    hire_date=None,
    base_salary=0,
    address: str = "",
    notes: str = "",
) -> Employee:
    """Foydalanuvchi (rol + nuqta) va xodim yozuvini bir tranzaksiyada yaratadi."""
    check_role_allowed(actor, role)
    check_branch_allowed(actor, branch.pk)
    with transaction.atomic():
        user = account_services.create_user(
            actor=actor,
            username=username,
            password=password,
            full_name=full_name,
            role=role,
            phone=phone,
            branch_ids=[branch.pk],
            default_branch_id=branch.pk,
        )
        return Employee.objects.create(
            user=user,
            employee_number=employee_number or f"E-{user.pk:05d}",
            department=department,
            position=position,
            branch=branch,
            hire_date=hire_date or timezone.localdate(),
            base_salary=base_salary,
            phone=phone,
            address=address,
            notes=notes,
        )


def terminate_employee(*, actor, employee: Employee, termination_date=None) -> Employee:
    """Ishdan bo'shatish: holat o'zgaradi va tizimga kirish o'chiriladi."""
    check_manageable(actor, employee)
    if employee.status == Employee.Status.TERMINATED:
        raise BusinessRuleError("Xodim allaqachon ishdan bo'shatilgan", code="already_terminated")
    with transaction.atomic():
        employee.status = Employee.Status.TERMINATED
        employee.termination_date = termination_date or timezone.localdate()
        employee.save(update_fields=["status", "termination_date", "updated_at"])
        account_services.update_user(actor=actor, user=employee.user, is_active=False)
    return employee
