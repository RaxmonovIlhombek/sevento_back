from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime
from decimal import Decimal

from django.db.models import Q, QuerySet
from django.utils import timezone

from core import settings_service

from .models import Category, PriceType, Product, ProductPrice, Unit

# --- kategoriyalar ---


def categories_queryset() -> QuerySet[Category]:
    return Category.objects.select_related("parent")


def category_tree(include_inactive: bool = True) -> list[dict]:
    """Ichma-ich daraxt: [{id, name, sort_order, is_active, parent, children: [...]}]."""
    qs = Category.objects.all()
    if not include_inactive:
        qs = qs.filter(is_active=True)
    nodes = {
        c.id: {
            "id": c.id,
            "name": c.name,
            "sort_order": c.sort_order,
            "is_active": c.is_active,
            "parent": c.parent_id,
            "children": [],
        }
        for c in qs
    }
    roots = []
    for node in nodes.values():
        parent = nodes.get(node["parent"])
        (parent["children"] if parent else roots).append(node)
    return roots


def descendant_ids(category_id: int) -> set[int]:
    """Kategoriya va uning barcha avlodlari id lari (filtr uchun)."""
    children = defaultdict(list)
    for cid, pid in Category.objects.values_list("id", "parent_id"):
        children[pid].append(cid)
    result, stack = set(), [category_id]
    while stack:
        current = stack.pop()
        if current in result:
            continue
        result.add(current)
        stack.extend(children.get(current, []))
    return result


def ancestor_ids(category: Category) -> list[int]:
    parents = dict(Category.objects.values_list("id", "parent_id"))
    result, current = [], parents.get(category.id)
    while current is not None and current not in result:
        result.append(current)
        current = parents.get(current)
    return result


# --- birliklar, narx turlari ---


def units_queryset() -> QuerySet[Unit]:
    return Unit.objects.all()


def price_types_queryset() -> QuerySet[PriceType]:
    return PriceType.objects.all()


def default_price_type() -> PriceType | None:
    return PriceType.objects.filter(is_default=True).first() or PriceType.objects.first()


# --- tovarlar ---


def products_queryset() -> QuerySet[Product]:
    return Product.objects.select_related("category", "unit")


def search_products(queryset: QuerySet[Product], text: str) -> QuerySet[Product]:
    text = text.strip()
    if not text:
        return queryset
    return queryset.filter(
        Q(name__icontains=text) | Q(sku__icontains=text) | Q(barcode__iexact=text)
    )


def get_product(product_id: int) -> Product | None:
    return products_queryset().filter(pk=product_id).first()


def effective_min_quantity(product: Product) -> Decimal:
    if product.min_quantity is not None:
        return product.min_quantity
    return Decimal(settings_service.get("inventory.default_min_quantity"))


# --- narxlar ---


def current_prices(
    product_ids: Iterable[int], branch_id: int | None = None, at: datetime | None = None
) -> dict[int, list[dict]]:
    """Har tovar uchun joriy narxlar ro'yxati (narx turi × valyuta).

    Nuqtaga xos narx (branch=branch_id) umumiy (branch=null) narxdan ustun.
    """
    at = at or timezone.now()
    ids = list(product_ids)
    if not ids:
        return {}
    rows = (
        ProductPrice.objects.filter(product_id__in=ids, valid_from__lte=at)
        .filter(Q(branch__isnull=True) | Q(branch_id=branch_id))
        .select_related("price_type", "currency")
        .order_by("product_id", "price_type_id", "currency_id", "-valid_from", "-id")
    )
    best: dict[tuple[int, int, int], ProductPrice] = {}
    for row in rows:
        key = (row.product_id, row.price_type_id, row.currency_id)
        existing = best.get(key)
        if existing is None:
            best[key] = row
            continue
        # xos narx umumiydan ustun; bir xil darajada eng so'nggisi (tartib bo'yicha birinchi)
        if existing.branch_id is None and row.branch_id is not None:
            best[key] = row
    result: dict[int, list[dict]] = defaultdict(list)
    for row in best.values():
        result[row.product_id].append(
            {
                "price_type": row.price_type.code,
                "price_type_name": row.price_type.name,
                "currency": row.currency.code,
                "amount": row.amount,
                "branch": row.branch_id,
                "valid_from": row.valid_from,
            }
        )
    for items in result.values():
        items.sort(key=lambda p: (p["price_type"], p["currency"]))
    return result


def current_price(
    product: Product, price_type: PriceType, currency_code: str, branch_id: int | None = None
) -> ProductPrice | None:
    rows = (
        ProductPrice.objects.filter(
            product=product,
            price_type=price_type,
            currency__code=currency_code,
            valid_from__lte=timezone.now(),
        )
        .filter(Q(branch__isnull=True) | Q(branch_id=branch_id))
        .order_by("-valid_from", "-id")
    )
    specific = next((r for r in rows if r.branch_id is not None), None)
    return specific or rows.first()


def price_history(product: Product) -> QuerySet[ProductPrice]:
    return product.prices.select_related("price_type", "currency", "branch", "created_by")
