from decimal import Decimal

from django.db.models import Count, F, OuterRef, Q, QuerySet, Subquery, Sum
from django.utils import timezone

from apps.currency import selectors as currency_selectors
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


# --- hisobotlar va dashboard uchun ---

IN, OUT = "in", "out"


def document_payment_totals(doc_type: str, doc_ids) -> list[dict]:
    """Hujjatlar (masalan davr savdolari) to'lovlari turlar bo'yicha, asosiy valyutada (net)."""
    rows = (
        Payment.objects.filter(document_type=doc_type, document_id__in=doc_ids)
        .values("method__name")
        .annotate(
            incoming=Sum("amount_base", filter=Q(direction=IN)),
            outgoing=Sum("amount_base", filter=Q(direction=OUT)),
        )
        .order_by("method__name")
    )
    return [
        {
            "method": r["method__name"],
            "amount_base": (r["incoming"] or Decimal(0)) - (r["outgoing"] or Decimal(0)),
        }
        for r in rows
    ]


def payments_summary(user, *, date_from, date_to, branch_id=None) -> list[dict]:
    """To'lov turi × valyuta: kirim, chiqim (qaytim, qaytarish), soni — davr bo'yicha."""
    qs = payments_queryset(user).filter(
        received_at__date__gte=date_from, received_at__date__lte=date_to
    )
    if branch_id:
        qs = qs.filter(branch_id=branch_id)
    return list(
        qs.values("method__name", "currency__code", "currency__decimal_places")
        .annotate(
            count=Count("id"),
            incoming=Sum("amount", filter=Q(direction=IN)),
            outgoing=Sum("amount", filter=Q(direction=OUT)),
            incoming_base=Sum("amount_base", filter=Q(direction=IN)),
            outgoing_base=Sum("amount_base", filter=Q(direction=OUT)),
        )
        .order_by("method__name", "currency__code")
    )


def cash_flow(user, *, date_from, date_to, branch_id=None, currency_code=None) -> list[dict]:
    """Kassa (nuqta × valyuta): boshlang'ich qoldiq, kirim, chiqim, yakuniy qoldiq."""
    tx = CashTransaction.objects.filter(cashbox=OuterRef("pk")).order_by("-created_at", "-id")
    period = Q(
        transactions__created_at__date__gte=date_from,
        transactions__created_at__date__lte=date_to,
    )
    qs = cashboxes_queryset(user).annotate(
        opening=Subquery(tx.filter(created_at__date__lt=date_from).values("balance_after")[:1]),
        closing=Subquery(tx.filter(created_at__date__lte=date_to).values("balance_after")[:1]),
        incoming=Sum("transactions__amount", filter=period & Q(transactions__direction=IN)),
        outgoing=Sum("transactions__amount", filter=period & Q(transactions__direction=OUT)),
    )
    if branch_id:
        qs = qs.filter(branch_id=branch_id)
    if currency_code:
        qs = qs.filter(currency__code=currency_code)
    return [
        {
            "branch": c.branch.name,
            "currency": c.currency.code,
            "decimal_places": c.currency.decimal_places,
            "opening": c.opening or Decimal(0),
            "incoming": c.incoming or Decimal(0),
            "outgoing": c.outgoing or Decimal(0),
            "closing": c.closing or Decimal(0),
        }
        for c in qs.order_by("branch__name", "currency__code")
    ]


def open_debts(user, *, branch_id=None, overdue_only=False, today=None) -> QuerySet[Debt]:
    today = today or timezone.localdate()
    qs = debts_queryset(user).filter(status=Debt.Status.OPEN)
    if branch_id:
        qs = qs.filter(branch_id=branch_id)
    if overdue_only:
        qs = qs.filter(due_date__lt=today)
    return qs.order_by("customer__name", "due_date", "id")


def cash_totals(user, *, branch_id=None) -> list[dict]:
    """Dashboard: kassalardagi naqd valyutalar bo'yicha."""
    qs = cashboxes_queryset(user)
    if branch_id:
        qs = qs.filter(branch_id=branch_id)
    return list(
        qs.values("currency__code", "currency__decimal_places")
        .annotate(balance=Sum("balance"))
        .order_by("currency__code")
    )


def debt_totals(user, *, branch_id=None, today=None) -> dict:
    """Dashboard: ochiq va muddati o'tgan qarzlar asosiy valyutada (joriy kurs)."""
    today = today or timezone.localdate()
    rows = (
        open_debts(user, branch_id=branch_id)
        .values("currency__code")
        .annotate(
            remaining=Sum(F("amount") - F("paid_amount") - F("returned_amount")),
            overdue=Sum(
                F("amount") - F("paid_amount") - F("returned_amount"),
                filter=Q(due_date__lt=today),
            ),
            overdue_count=Count("id", filter=Q(due_date__lt=today)),
        )
        .order_by()
    )
    open_base = overdue_base = Decimal(0)
    overdue_count = 0
    for r in rows:
        rate = currency_selectors.rate_to_base(r["currency__code"])
        open_base += (r["remaining"] or 0) * rate
        overdue_base += (r["overdue"] or 0) * rate
        overdue_count += r["overdue_count"]
    return {"open_base": open_base, "overdue_base": overdue_base, "overdue_count": overdue_count}
