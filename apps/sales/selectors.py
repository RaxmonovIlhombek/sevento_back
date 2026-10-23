from datetime import date
from decimal import Decimal

from django.db.models import Count, Prefetch, QuerySet, Sum
from django.utils import timezone

from apps.catalog import selectors as catalog_selectors
from apps.inventory import selectors as inventory_selectors
from apps.payments import selectors as payment_selectors
from core.access import scope_queryset_to_user

from .models import Sale, SaleItem
from .pricing import resolve_prices


def _scoped(user) -> QuerySet[Sale]:
    return scope_queryset_to_user(Sale.objects.all(), user, "branch")


def sales_queryset(user) -> QuerySet[Sale]:
    qs = _scoped(user).select_related("branch", "seller", "currency", "price_type", "cancelled_by")
    return qs.annotate(items_count=Count("items"))


def sale_detail_queryset(user) -> QuerySet[Sale]:
    return sales_queryset(user).prefetch_related(
        Prefetch("items", queryset=SaleItem.objects.select_related("product", "product__unit"))
    )


def sale_payments(sale: Sale):
    return payment_selectors.payments_for_document("sale", sale.pk)


def pos_products(
    *,
    branch_id: int,
    currency,
    price_type,
    search: str = "",
    barcode: str = "",
    limit: int = 20,
) -> list[dict]:
    """Kassa qidiruvi: faol tovarlar + shu nuqta qoldig'i + savdo valyutasidagi narx."""
    qs = catalog_selectors.products_queryset().filter(is_active=True).select_related("unit")
    if barcode:
        qs = qs.filter(barcode=barcode.strip())
    elif search:
        qs = catalog_selectors.search_products(qs, search)
    products = list(qs.order_by("name")[:limit])
    ids = [p.pk for p in products]
    prices = resolve_prices(
        ids,
        price_type_code=price_type.code,
        currency_code=currency.code,
        decimal_places=currency.decimal_places,
        branch_id=branch_id,
    )
    stock = inventory_selectors.quantities(branch_id, ids)
    return [
        {
            "id": p.pk,
            "sku": p.sku,
            "barcode": p.barcode,
            "name": p.name,
            "unit_code": p.unit.code,
            "unit_decimal_places": p.unit.decimal_places,
            "price": prices.get(p.pk),
            "stock": stock.get(p.pk, Decimal(0)),
        }
        for p in products
    ]


def daily_summary(user, *, on: date | None = None, branch_id: int | None = None) -> dict:
    """Kun bo'yicha savdo xulosasi (dashboard): valyuta kesimida soni va summasi, jami asosiy
    valyutada, tannarx va foyda."""
    on = on or timezone.localdate()
    qs = _scoped(user).filter(completed_at__date=on)  # annotatsiyasiz: JOIN summani ko'paytirmasin
    if branch_id:
        qs = qs.filter(branch_id=branch_id)
    completed = qs.filter(status=Sale.Status.COMPLETED)
    by_currency = [
        {"currency": row["currency__code"], "count": row["count"], "total": row["total"]}
        for row in completed.values("currency__code")
        .annotate(count=Count("id"), total=Sum("total"))
        .order_by("currency__code")
    ]
    totals = completed.aggregate(
        count=Count("id"), total_base=Sum("total_base"), cost_base=Sum("cost_base")
    )
    total_base = totals["total_base"] or Decimal(0)
    cost_base = totals["cost_base"] or Decimal(0)
    return {
        "date": on,
        "branch": branch_id,
        "count": totals["count"] or 0,
        "cancelled_count": qs.filter(status=Sale.Status.CANCELLED).count(),
        "by_currency": by_currency,
        "total_base": total_base,
        "cost_base": cost_base,
        "profit_base": total_base - cost_base,
    }
