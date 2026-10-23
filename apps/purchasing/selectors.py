from django.db.models import Count, Prefetch, QuerySet

from core.access import scope_queryset_to_user

from .models import ExpenseType, Purchase, PurchaseExpense, PurchaseItem, Supplier


def suppliers_queryset() -> QuerySet[Supplier]:
    return Supplier.objects.annotate(purchases_count=Count("purchases"))


def expense_types_queryset() -> QuerySet[ExpenseType]:
    return ExpenseType.objects.all()


def purchases_queryset(user) -> QuerySet[Purchase]:
    qs = Purchase.objects.select_related(
        "branch", "supplier", "currency", "created_by", "received_by", "cancelled_by"
    ).annotate(items_count=Count("items"))
    return scope_queryset_to_user(qs, user, "branch")


def purchase_detail_queryset(user) -> QuerySet[Purchase]:
    return purchases_queryset(user).prefetch_related(
        Prefetch(
            "items",
            queryset=PurchaseItem.objects.select_related("product", "product__unit"),
        ),
        Prefetch(
            "expenses",
            queryset=PurchaseExpense.objects.select_related("expense_type", "currency"),
        ),
    )


def received_purchases(user, *, date_from, date_to, branch_id=None, supplier_id=None):
    """Hisobot: davrda qabul qilingan kirimlar (qabul sanasi bo'yicha)."""
    qs = purchases_queryset(user).filter(
        status=Purchase.Status.RECEIVED,
        received_at__date__gte=date_from,
        received_at__date__lte=date_to,
    )
    if branch_id:
        qs = qs.filter(branch_id=branch_id)
    if supplier_id:
        qs = qs.filter(supplier_id=supplier_id)
    return qs.order_by("received_at", "id")
