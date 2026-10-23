from decimal import Decimal

from django.db.models import F, QuerySet, Sum
from django.utils import timezone

from core.access import scope_queryset_to_user

from .models import (
    Cashbox,
    CashFlowCategory,
    CashShift,
    CashTransaction,
    Customer,
    CustomerLedgerEntry,
    Debt,
    Payment,
    PaymentMethod,
)


def payment_methods_queryset() -> QuerySet[PaymentMethod]:
    return PaymentMethod.objects.all()


def active_payment_methods() -> QuerySet[PaymentMethod]:
    return PaymentMethod.objects.filter(is_active=True)


def cash_method() -> PaymentMethod | None:
    """Qaytim beriladigan naqd to'lov turi (birinchi faol is_cash)."""
    return active_payment_methods().filter(is_cash=True).first()


def cash_categories_queryset() -> QuerySet[CashFlowCategory]:
    return CashFlowCategory.objects.all()


def cashboxes_queryset(user) -> QuerySet[Cashbox]:
    qs = Cashbox.objects.select_related("branch", "currency")
    return scope_queryset_to_user(qs, user, "branch")


def cash_transactions_queryset(user) -> QuerySet[CashTransaction]:
    qs = CashTransaction.objects.select_related(
        "cashbox", "cashbox__branch", "cashbox__currency", "category", "payment", "created_by"
    )
    return scope_queryset_to_user(qs, user, "cashbox__branch")


def payments_for_document(doc_type: str, doc_id: int) -> list[Payment]:
    return list(
        Payment.objects.filter(document_type=doc_type, document_id=doc_id)
        .select_related("method", "currency", "received_by")
        .order_by("received_at", "id")
    )


def cashbox_balance(branch_id: int, currency_code: str) -> "Cashbox | None":
    return (
        Cashbox.objects.filter(branch_id=branch_id, currency__code=currency_code.upper())
        .select_related("currency")
        .first()
    )


# --- mijozlar va qarzlar ---


def customers_queryset() -> QuerySet[Customer]:
    return Customer.objects.all()


def customer_balances(customer_ids) -> dict[int, dict[str, Decimal]]:
    """Ochiq qarz qoldig'i: {mijoz id: {valyuta kodi: summa}}."""
    rows = (
        Debt.objects.filter(customer_id__in=list(customer_ids), status=Debt.Status.OPEN)
        .values("customer_id", "currency__code")
        .annotate(total=Sum(F("amount") - F("paid_amount") - F("returned_amount")))
        .order_by()
    )
    result: dict[int, dict[str, Decimal]] = {}
    for row in rows:
        result.setdefault(row["customer_id"], {})[row["currency__code"]] = row["total"]
    return result


def overdue_customer_ids(customer_ids, today=None) -> set[int]:
    today = today or timezone.localdate()
    return set(
        Debt.objects.filter(
            customer_id__in=list(customer_ids), status=Debt.Status.OPEN, due_date__lt=today
        ).values_list("customer_id", flat=True)
    )


def debts_queryset(user) -> QuerySet[Debt]:
    qs = Debt.objects.select_related("customer", "currency", "branch", "created_by").annotate(
        remaining_amount=F("amount") - F("paid_amount") - F("returned_amount")
    )
    return scope_queryset_to_user(qs, user, "branch")


def customer_debts(customer_id: int) -> QuerySet[Debt]:
    """Mijoz kartasi uchun — barcha nuqtalar (kredit qarori umumiy balansga qarab)."""
    return (
        Debt.objects.filter(customer_id=customer_id)
        .select_related("currency", "branch")
        .annotate(remaining_amount=F("amount") - F("paid_amount") - F("returned_amount"))
    )


def ledger_queryset(customer_id: int) -> QuerySet[CustomerLedgerEntry]:
    return CustomerLedgerEntry.objects.filter(customer_id=customer_id).select_related(
        "currency", "created_by", "payment", "payment__method"
    )


def payments_queryset(user) -> QuerySet[Payment]:
    qs = Payment.objects.select_related(
        "method", "currency", "branch", "customer", "received_by", "reversal_of"
    )
    return scope_queryset_to_user(qs, user, "branch")


def document_debt(doc_type: str, doc_id: int) -> Debt | None:
    return (
        Debt.objects.filter(document_type=doc_type, document_id=doc_id)
        .select_related("currency")
        .order_by("-id")
        .first()
    )


# --- smena ---


def shifts_queryset(user) -> QuerySet[CashShift]:
    qs = CashShift.objects.select_related("branch", "opened_by", "closed_by").prefetch_related(
        "balances__cashbox__currency"
    )
    return scope_queryset_to_user(qs, user, "branch")


def current_shift(branch_id: int) -> CashShift | None:
    return (
        CashShift.objects.filter(branch_id=branch_id, status=CashShift.Status.OPEN)
        .select_related("opened_by")
        .prefetch_related("balances__cashbox__currency")
        .first()
    )
