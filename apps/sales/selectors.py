from datetime import date
from decimal import Decimal

from django.db.models import (
    Count,
    DecimalField,
    ExpressionWrapper,
    F,
    Prefetch,
    QuerySet,
    Sum,
)
from django.db.models.functions import TruncDate, TruncHour
from django.utils import timezone

from apps.catalog import selectors as catalog_selectors
from apps.inventory import selectors as inventory_selectors
from apps.payments import selectors as payment_selectors
from core.access import scope_queryset_to_user

from .models import Sale, SaleItem, SaleReturn, SaleReturnItem
from .pricing import resolve_prices


def _scoped(user) -> QuerySet[Sale]:
    return scope_queryset_to_user(Sale.objects.all(), user, "branch")


def sales_queryset(user) -> QuerySet[Sale]:
    qs = _scoped(user).select_related(
        "branch", "seller", "currency", "price_type", "cancelled_by", "customer"
    )
    return qs.annotate(items_count=Count("items"))


def sale_detail_queryset(user) -> QuerySet[Sale]:
    return sales_queryset(user).prefetch_related(
        Prefetch("items", queryset=SaleItem.objects.select_related("product", "product__unit")),
        Prefetch(
            "returns",
            queryset=SaleReturn.objects.select_related("created_by", "refund_method").order_by(
                "created_at", "id"
            ),
        ),
    )


def returns_queryset(user) -> QuerySet[SaleReturn]:
    qs = SaleReturn.objects.select_related(
        "branch", "sale", "customer", "currency", "refund_method", "created_by"
    ).annotate(items_count=Count("items"))
    return scope_queryset_to_user(qs, user, "branch")


def return_detail_queryset(user) -> QuerySet[SaleReturn]:
    return returns_queryset(user).prefetch_related(
        Prefetch(
            "items",
            queryset=SaleReturnItem.objects.select_related("product", "product__unit"),
        )
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
    ids: list[int] | None = None,
    limit: int = 20,
) -> list[dict]:
    """Kassa qidiruvi: faol tovarlar + shu nuqta qoldig'i + savdo valyutasidagi narx.

    `ids` — savatdagi tovarlar narxini yangilash uchun (sahifa qayta ochilganda, narx o'zgarganda).
    """
    qs = catalog_selectors.products_queryset().filter(is_active=True).select_related("unit")
    if ids:
        qs = qs.filter(pk__in=ids)
    elif barcode:
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
    returns = scope_queryset_to_user(SaleReturn.objects.all(), user, "branch").filter(
        created_at__date=on
    )
    if branch_id:
        returns = returns.filter(branch_id=branch_id)
    returned = returns.aggregate(
        count=Count("id"), total_base=Sum("total_base"), cost_base=Sum("cost_base")
    )
    total_base = totals["total_base"] or Decimal(0)
    cost_base = totals["cost_base"] or Decimal(0)
    returns_total_base = returned["total_base"] or Decimal(0)
    returns_cost_base = returned["cost_base"] or Decimal(0)
    return {
        "date": on,
        "branch": branch_id,
        "count": totals["count"] or 0,
        "cancelled_count": qs.filter(status=Sale.Status.CANCELLED).count(),
        "by_currency": by_currency,
        "total_base": total_base,
        "cost_base": cost_base,
        "returns_count": returned["count"] or 0,
        "returns_total_base": returns_total_base,
        # foyda — shu kungi qaytarishlar (sotuv narxi va tannarxi) ayirilgan
        "profit_base": (total_base - returns_total_base) - (cost_base - returns_cost_base),
    }


# --- hisobotlar va dashboard uchun (reports app faqat shularni o'qiydi) ---

MONEY = DecimalField(max_digits=24, decimal_places=8)

# guruhlash: kalit → (savdo maydonlari, qaytarish maydonlari)
_GROUPS = {
    "day": ({"key": TruncDate("completed_at")}, {"key": TruncDate("created_at")}),
    "hour": ({"key": TruncHour("completed_at")}, {"key": TruncHour("created_at")}),
    "branch": (
        {"key": F("branch_id"), "label": F("branch__name")},
        {"key": F("branch_id"), "label": F("branch__name")},
    ),
    "seller": (
        {"key": F("seller_id"), "label": F("seller__full_name")},
        {"key": F("sale__seller_id"), "label": F("sale__seller__full_name")},
    ),
}


def period_sales(user, *, date_from: date, date_to: date, branch_id: int | None = None):
    """Davrdagi yakunlangan savdolar (nuqta chegarasi bilan)."""
    qs = _scoped(user).filter(
        status=Sale.Status.COMPLETED,
        completed_at__date__gte=date_from,
        completed_at__date__lte=date_to,
    )
    return qs.filter(branch_id=branch_id) if branch_id else qs


def period_returns(user, *, date_from: date, date_to: date, branch_id: int | None = None):
    qs = scope_queryset_to_user(SaleReturn.objects.all(), user, "branch").filter(
        created_at__date__gte=date_from, created_at__date__lte=date_to
    )
    return qs.filter(branch_id=branch_id) if branch_id else qs


def sales_by_group(user, *, date_from, date_to, branch_id=None, group_by="day") -> list[dict]:
    """[{key, label?, count, revenue_base, cost_base, discount_base}] (asosiy valyutada)."""
    fields, _ = _GROUPS[group_by]
    return list(
        period_sales(user, date_from=date_from, date_to=date_to, branch_id=branch_id)
        .annotate(**fields)
        .values(*fields)
        .annotate(
            count=Count("id"),
            revenue_base=Sum("total_base"),
            cost_base=Sum("cost_base"),
            discount_base=Sum(
                ExpressionWrapper(F("discount_total") * F("rate_to_base"), output_field=MONEY)
            ),
        )
        .order_by("key")
    )


def returns_by_group(user, *, date_from, date_to, branch_id=None, group_by="day") -> list[dict]:
    """[{key, label?, count, total_base, cost_base}] — qaytarish sanasi bo'yicha."""
    _, fields = _GROUPS[group_by]
    return list(
        period_returns(user, date_from=date_from, date_to=date_to, branch_id=branch_id)
        .annotate(**fields)
        .values(*fields)
        .annotate(count=Count("id"), total_base=Sum("total_base"), cost_base=Sum("cost_base"))
        .order_by("key")
    )


def _product_fields(group_by: str, prefix: str) -> list[str]:
    if group_by == "category":
        return [f"{prefix}category_id", f"{prefix}category__name"]
    return [
        f"{prefix}id",
        f"{prefix}name",
        f"{prefix}sku",
        f"{prefix}unit__code",
        f"{prefix}unit__decimal_places",
    ]


def product_sales(
    user, *, date_from, date_to, branch_id=None, category_ids=None, group_by="product"
) -> list[dict]:
    """Tovar (yoki kategoriya) bo'yicha: qty, revenue_base, cost_base."""
    sales = period_sales(user, date_from=date_from, date_to=date_to, branch_id=branch_id)
    qs = SaleItem.objects.filter(sale__in=sales)
    if category_ids:
        qs = qs.filter(product__category_id__in=category_ids)
    return list(
        qs.values(*_product_fields(group_by, "product__"))
        .annotate(
            qty=Sum("quantity"),
            revenue_base=Sum(
                ExpressionWrapper(F("line_total") * F("sale__rate_to_base"), output_field=MONEY)
            ),
            cost_base=Sum("cost_base"),
        )
        .order_by()
    )


def product_returns(
    user, *, date_from, date_to, branch_id=None, category_ids=None, group_by="product"
) -> list[dict]:
    returns = period_returns(user, date_from=date_from, date_to=date_to, branch_id=branch_id)
    qs = SaleReturnItem.objects.filter(sale_return__in=returns)
    if category_ids:
        qs = qs.filter(product__category_id__in=category_ids)
    return list(
        qs.values(*_product_fields(group_by, "product__"))
        .annotate(
            qty=Sum("quantity"),
            total_base=Sum(
                ExpressionWrapper(
                    F("amount") * F("sale_return__sale__rate_to_base"), output_field=MONEY
                )
            ),
            cost_base=Sum("cost_base"),
        )
        .order_by()
    )


def returns_report(user, *, date_from, date_to, branch_id=None) -> QuerySet[SaleReturn]:
    return (
        period_returns(user, date_from=date_from, date_to=date_to, branch_id=branch_id)
        .select_related("sale", "branch", "customer", "currency", "refund_method", "created_by")
        .order_by("created_at", "id")
    )


def payment_method_totals(user, *, date_from, date_to, branch_id=None) -> list[dict]:
    """Dashboard: savdo to'lovlari to'lov turlari bo'yicha (asosiy valyutada)."""
    sales = period_sales(user, date_from=date_from, date_to=date_to, branch_id=branch_id)
    return payment_selectors.document_payment_totals("sale", sales.values("id"))
