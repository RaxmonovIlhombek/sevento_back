from django.db.models import QuerySet

from core.access import scope_queryset_to_user

from .models import Cashbox, CashFlowCategory, CashTransaction, Payment, PaymentMethod


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
