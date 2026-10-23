"""Qoldiqni o'zgartiradigan yagona joy. Kirim, savdo, ko'chirish, inventarizatsiya, hisobdan
chiqarish — hammasi shu funksiyalardan o'tadi (boshqa app lar StockLevel/Batch ga yozmaydi).

Har funksiya chaqiruvchining tranzaksiyasi ichida ishlaydi; StockLevel qatori select_for_update
bilan qulflanadi (nuqta × tovar bo'yicha ketma-ketlik), keyin partiyalar.
"""

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone

from apps.catalog import selectors as catalog_selectors

from . import events
from .costing import get_strategy
from .exceptions import BatchConsumed, InsufficientStock
from .models import Batch, StockLevel, StockMovement
from .types import DocRef, IssueResult, MovementType

MONEY_PLACES = Decimal("0.0001")
UNIT_COST_PLACES = Decimal("0.000001")


def _lock_level(branch_id: int, product_id: int) -> StockLevel:
    StockLevel.objects.get_or_create(branch_id=branch_id, product_id=product_id)
    return StockLevel.objects.select_for_update().get(branch_id=branch_id, product_id=product_id)


def _effective_min(level: StockLevel, product) -> Decimal:
    if level.min_quantity is not None:
        return level.min_quantity
    return catalog_selectors.effective_min_quantity(product)


def _apply_delta(
    *, actor, level: StockLevel, delta: Decimal, movement_type: str, doc: DocRef
) -> StockLevel:
    """Qoldiqni yangilaydi, hodisalarni chiqaradi, minimal chegarani kuzatadi."""
    before = level.quantity
    level.quantity = before + delta
    if level.quantity < 0:  # MB constraint ham ushlaydi; bu yerda tushunarli xabar uchun
        raise InsufficientStock()

    product = catalog_selectors.get_product(level.product_id)
    min_qty = _effective_min(level, product)
    now_below = min_qty > 0 and level.quantity < min_qty
    crossed_down = now_below and not level.below_minimum
    level.below_minimum = now_below
    level.save(update_fields=["quantity", "below_minimum", "updated_at"])

    events.StockChanged.publish_from(
        actor=actor,
        branch_id=level.branch_id,
        product_id=level.product_id,
        quantity_before=before,
        quantity_after=level.quantity,
        delta=delta,
        movement_type=movement_type,
        document_type=doc.type,
        document_id=doc.id,
        document_number=doc.number,
    )
    if crossed_down:
        events.StockBelowMinimum.publish_from(
            actor=actor,
            branch_id=level.branch_id,
            product_id=level.product_id,
            product_name=product.name,
            quantity=level.quantity,
            min_quantity=min_qty,
            unit=product.unit.code,
        )
    return level


def receive_stock(
    *,
    actor,
    branch_id: int,
    product_id: int,
    quantity: Decimal,
    unit_cost_base: Decimal,
    movement_type: str,
    doc: DocRef,
    received_at: datetime | None = None,
    parent_batch_id: int | None = None,
) -> Batch:
    """Kirim: partiya + harakat + qoldiq. quantity > 0."""
    if quantity <= 0:
        raise ValueError("receive_stock: quantity > 0 bo'lishi kerak")
    unit_cost_base = Decimal(unit_cost_base).quantize(UNIT_COST_PLACES, rounding=ROUND_HALF_UP)
    with transaction.atomic():
        level = _lock_level(branch_id, product_id)
        batch = get_strategy().on_receive(
            branch_id=branch_id,
            product_id=product_id,
            quantity=quantity,
            unit_cost_base=unit_cost_base,
            source=doc,
            received_at=received_at,
            parent_batch_id=parent_batch_id,
        )
        level = _apply_delta(
            actor=actor, level=level, delta=quantity, movement_type=movement_type, doc=doc
        )
        StockMovement.objects.create(
            branch_id=branch_id,
            product_id=product_id,
            batch=batch,
            type=movement_type,
            quantity=quantity,
            unit_cost_base=unit_cost_base,
            total_cost_base=(quantity * unit_cost_base).quantize(MONEY_PLACES, ROUND_HALF_UP),
            balance_after=level.quantity,
            document_type=doc.type,
            document_id=doc.id,
            document_number=doc.number,
            created_by=actor,
        )
    return batch


def issue_stock(
    *,
    actor,
    branch_id: int,
    product_id: int,
    quantity: Decimal,
    movement_type: str,
    doc: DocRef,
) -> IssueResult:
    """Chiqim tannarx strategiyasi (FIFO) bo'yicha. Yetmasa InsufficientStock (409)."""
    if quantity <= 0:
        raise ValueError("issue_stock: quantity > 0 bo'lishi kerak")
    with transaction.atomic():
        level = _lock_level(branch_id, product_id)
        allocations = get_strategy().allocate_issue(
            branch_id=branch_id, product_id=product_id, quantity=quantity
        )
        level = _apply_delta(
            actor=actor, level=level, delta=-quantity, movement_type=movement_type, doc=doc
        )
        now = timezone.now()
        total = Decimal(0)
        balance = level.quantity + quantity
        rows = []
        for alloc in allocations:
            cost = (alloc.quantity * alloc.unit_cost_base).quantize(MONEY_PLACES, ROUND_HALF_UP)
            total += cost
            balance -= alloc.quantity
            rows.append(
                StockMovement(
                    branch_id=branch_id,
                    product_id=product_id,
                    batch_id=alloc.batch_id,
                    type=movement_type,
                    quantity=-alloc.quantity,
                    unit_cost_base=alloc.unit_cost_base,
                    total_cost_base=-cost,
                    balance_after=balance,
                    document_type=doc.type,
                    document_id=doc.id,
                    document_number=doc.number,
                    created_by=actor,
                    created_at=now,
                )
            )
        StockMovement.objects.bulk_create(rows)
    return IssueResult(allocations=allocations, total_cost_base=total)


def reverse_receipt(*, actor, doc_type: str, doc_id: int, doc_number: str = "") -> int:
    """Kirimni bekor qilish (partiyalari tegilmagan bo'lsagina); qaytarilgan partiyalar soni."""
    with transaction.atomic():
        batches = list(
            Batch.objects.select_for_update()
            .filter(source_type=doc_type, source_id=doc_id)
            .order_by("id")
        )
        if any(b.quantity_remaining != b.quantity_initial for b in batches):
            raise BatchConsumed()
        doc = DocRef(type=doc_type, id=doc_id, number=doc_number)
        for batch in batches:
            if batch.quantity_initial == 0:
                continue
            level = _lock_level(batch.branch_id, batch.product_id)
            qty = batch.quantity_initial
            batch.quantity_remaining = Decimal(0)
            batch.save(update_fields=["quantity_remaining"])
            level = _apply_delta(
                actor=actor,
                level=level,
                delta=-qty,
                movement_type=MovementType.PURCHASE_CANCEL,
                doc=doc,
            )
            StockMovement.objects.create(
                branch_id=batch.branch_id,
                product_id=batch.product_id,
                batch=batch,
                type=MovementType.PURCHASE_CANCEL,
                quantity=-qty,
                unit_cost_base=batch.unit_cost_base,
                total_cost_base=-(qty * batch.unit_cost_base).quantize(MONEY_PLACES, ROUND_HALF_UP),
                balance_after=level.quantity,
                document_type=doc_type,
                document_id=doc_id,
                document_number=doc_number,
                created_by=actor,
            )
    return len(batches)


def set_min_quantity(*, actor, level: StockLevel, min_quantity: Decimal | None) -> StockLevel:
    """Nuqtaga xos minimal qoldiq (null — tovar/sozlama defaulti)."""
    with transaction.atomic():
        level = StockLevel.objects.select_for_update().get(pk=level.pk)
        old = level.min_quantity
        level.min_quantity = min_quantity
        product = catalog_selectors.get_product(level.product_id)
        min_qty = _effective_min(level, product)
        level.below_minimum = min_qty > 0 and level.quantity < min_qty
        level.save(update_fields=["min_quantity", "below_minimum", "updated_at"])
        if old != min_quantity:
            events.MinQuantityChanged.publish_from(
                actor=actor,
                branch_id=level.branch_id,
                product_id=level.product_id,
                old_value=old,
                new_value=min_quantity,
            )
    return level
