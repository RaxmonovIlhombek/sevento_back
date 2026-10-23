from datetime import datetime
from decimal import Decimal

from django.db import transaction

from core.exceptions import BusinessRuleError

from . import events, selectors
from .models import Category, PriceType, Product, ProductPrice, Unit


def _apply_changes(instance, fields: dict) -> dict:
    changes = {}
    for name, value in fields.items():
        old = getattr(instance, name)
        if old != value:
            changes[name] = {"old": _plain(old), "new": _plain(value)}
            setattr(instance, name, value)
    return changes


def _plain(value):
    if hasattr(value, "pk"):
        return value.pk
    return value


# --- kategoriyalar ---


def create_category(*, actor, **fields) -> Category:
    with transaction.atomic():
        category = Category.objects.create(**fields)
        events.CategoryCreated.publish_from(
            actor=actor,
            category_id=category.pk,
            category_name=category.name,
            parent_id=category.parent_id,
        )
    return category


def update_category(*, actor, category: Category, **fields) -> Category:
    parent = fields.get("parent")
    if parent is not None:
        if parent.pk == category.pk or parent.pk in selectors.descendant_ids(category.pk):
            raise BusinessRuleError(
                "Kategoriya o'zining avlodi ichiga ko'chirilmaydi",
                code="category_cycle",
                status_code=400,
                details=[{"field": "parent", "code": "category_cycle", "message": "Sikl"}],
            )
    with transaction.atomic():
        changes = _apply_changes(category, fields)
        category.save()
        if changes:
            events.CategoryUpdated.publish_from(
                actor=actor, category_id=category.pk, changes=changes
            )
    return category


# --- birliklar, narx turlari ---


def save_unit(*, actor, unit: Unit | None = None, **fields) -> Unit:
    with transaction.atomic():
        if unit is None:
            unit = Unit.objects.create(**fields)
            changes = {}
        else:
            changes = _apply_changes(unit, fields)
            unit.save()
        events.UnitSaved.publish_from(actor=actor, unit_id=unit.pk, code=unit.code, changes=changes)
    return unit


def save_price_type(*, actor, price_type: PriceType | None = None, **fields) -> PriceType:
    with transaction.atomic():
        if price_type is None:
            price_type = PriceType.objects.create(**fields)
            changes = {}
        else:
            changes = _apply_changes(price_type, fields)
            price_type.save()
        if price_type.is_default:
            PriceType.objects.exclude(pk=price_type.pk).filter(is_default=True).update(
                is_default=False
            )
        events.PriceTypeSaved.publish_from(
            actor=actor, price_type_id=price_type.pk, code=price_type.code, changes=changes
        )
    return price_type


# --- tovarlar ---


def create_product(*, actor, **fields) -> Product:
    fields["sku"] = fields["sku"].strip().upper()
    fields["barcode"] = (fields.get("barcode") or "").strip()
    with transaction.atomic():
        product = Product.objects.create(**fields)
        events.ProductCreated.publish_from(
            actor=actor, product_id=product.pk, sku=product.sku, product_name=product.name
        )
    return product


def update_product(*, actor, product: Product, **fields) -> Product:
    if "sku" in fields:
        fields["sku"] = fields["sku"].strip().upper()
    if "barcode" in fields:
        fields["barcode"] = (fields.get("barcode") or "").strip()
    with transaction.atomic():
        changes = _apply_changes(product, fields)
        product.save()
        if changes:
            events.ProductUpdated.publish_from(
                actor=actor, product_id=product.pk, sku=product.sku, changes=changes
            )
    return product


def set_price(
    *,
    actor,
    product: Product,
    price_type: PriceType,
    currency,
    amount: Decimal,
    branch=None,
    valid_from: datetime | None = None,
) -> ProductPrice:
    """Yangi narx qatori (tarix saqlanadi). amount < 0 bo'lmasin."""
    if amount < 0:
        raise BusinessRuleError("Narx manfiy bo'lmasin", code="invalid_price", status_code=400)
    with transaction.atomic():
        previous = selectors.current_price(
            product, price_type, currency.code, branch.pk if branch else None
        )
        row = ProductPrice.objects.create(
            product=product,
            price_type=price_type,
            currency=currency,
            branch=branch,
            amount=amount,
            created_by=actor,
            **({"valid_from": valid_from} if valid_from else {}),
        )
        events.ProductPriceChanged.publish_from(
            actor=actor,
            branch_id=branch.pk if branch else None,
            product_id=product.pk,
            price_type=price_type.code,
            currency=currency.code,
            old_amount=previous.amount if previous else None,
            new_amount=amount,
        )
    return row
