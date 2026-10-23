"""Inventarizatsiya: yaratish (hisobdagi qoldiqlar ro'yxati) → sanash → yakunlash.

Yakunlashda har sanalgan qator joriy qoldiq bilan solishtiriladi (qulf ostida): ortiqcha — yangi
partiya (oxirgi kirim tannarxi), kamomad — FIFO chiqim. Sanalmagan (bo'sh) qatorlar o'tkazib
yuboriladi — qoldiq o'zgarmaydi.
"""

from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.catalog import selectors as catalog_selectors
from core.access import ensure_branch_access
from core.exceptions import InvalidStatusTransition
from core.numbering import next_number

from .. import events
from ..exceptions import CountEmpty, CountInProgress
from ..models import StockCount, StockCountItem, StockLevel
from ..selectors import latest_unit_cost
from ..types import DocRef
from .common import precision_error, validation_error
from .stock import adjust_to_counted

DOC_TYPE = "stock_count"
NUMBER_PREFIX = "INV"


def _locked_draft(count: StockCount) -> StockCount:
    count = StockCount.objects.select_for_update().get(pk=count.pk)
    if count.status != StockCount.Status.DRAFT:
        raise InvalidStatusTransition("Inventarizatsiya yakunlangan yoki bekor qilingan")
    return count


def create_count(
    *, actor, branch, category=None, include_zero: bool = False, note: str = ""
) -> StockCount:
    """Nuqta (ixtiyoriy: kategoriya) qoldiqlari ro'yxati bilan ochiladi; nuqtada bittadan ochiq."""
    ensure_branch_access(actor, branch.pk)
    levels = StockLevel.objects.filter(branch=branch, product__is_active=True)
    if not include_zero:
        levels = levels.filter(quantity__gt=0)
    if category is not None:
        levels = levels.filter(
            product__category_id__in=catalog_selectors.descendant_ids(category.pk)
        )
    try:
        with transaction.atomic():
            if StockCount.objects.filter(branch=branch, status=StockCount.Status.DRAFT).exists():
                raise CountInProgress()
            count = StockCount.objects.create(
                number=next_number(
                    doc_type=NUMBER_PREFIX, branch_id=branch.pk, branch_code=branch.code
                ),
                branch=branch,
                category=category,
                note=note,
                created_by=actor,
            )
            rows = StockCountItem.objects.bulk_create(
                [
                    StockCountItem(
                        count=count, product_id=level.product_id, expected_quantity=level.quantity
                    )
                    for level in levels.only("product_id", "quantity")
                ]
            )
            events.StockCountCreated.publish_from(
                actor=actor,
                branch_id=branch.pk,
                count_id=count.pk,
                number=count.number,
                items_count=len(rows),
            )
    except IntegrityError:  # parallel yaratish — unique constraint ushladi
        raise CountInProgress() from None
    return count


def set_counted(*, actor, count: StockCount, items: list[dict]) -> StockCount:
    """Sanalgan miqdorlar [{product, counted_quantity}] (null — sanalmagan), yangi tovar ham."""
    ensure_branch_access(actor, count.branch_id)
    errors = []
    for index, item in enumerate(items):
        qty = item["counted_quantity"]
        if qty is not None:
            error = precision_error(item["product"], qty, f"items.{index}.counted_quantity")
            if error:
                errors.append(error)
    if errors:
        raise validation_error("Sanalgan miqdorlarda xato bor", errors)
    with transaction.atomic():
        count = _locked_draft(count)
        existing = {row.product_id: row for row in count.items.all()}
        new_ids = [i["product"].pk for i in items if i["product"].pk not in existing]
        current = dict(
            StockLevel.objects.filter(
                branch_id=count.branch_id, product_id__in=new_ids
            ).values_list("product_id", "quantity")
        )
        to_update, to_create = [], []
        for item in items:
            product = item["product"]
            row = existing.get(product.pk)
            if row is None:
                to_create.append(
                    StockCountItem(
                        count=count,
                        product=product,
                        expected_quantity=current.get(product.pk, Decimal(0)),
                        counted_quantity=item["counted_quantity"],
                    )
                )
            else:
                row.counted_quantity = item["counted_quantity"]
                to_update.append(row)
        StockCountItem.objects.bulk_update(to_update, ["counted_quantity"])
        StockCountItem.objects.bulk_create(to_create)
        count.save(update_fields=["updated_at"])
    return count


def complete_count(*, actor, count: StockCount) -> StockCount:
    ensure_branch_access(actor, count.branch_id)
    with transaction.atomic():
        count = _locked_draft(count)
        rows = [r for r in count.items.all() if r.counted_quantity is not None]
        if not rows:
            raise CountEmpty()
        surplus_cost = shortage_cost = Decimal(0)
        surplus_items = shortage_items = 0
        for row in sorted(rows, key=lambda r: r.product_id):
            unit_cost = latest_unit_cost(count.branch_id, row.product_id)
            expected, diff, cost = adjust_to_counted(
                actor=actor,
                branch_id=count.branch_id,
                product_id=row.product_id,
                counted=row.counted_quantity,
                surplus_unit_cost_base=unit_cost,
                doc=DocRef(type=DOC_TYPE, id=count.pk, number=count.number, line_id=row.pk),
            )
            row.expected_quantity = expected
            row.difference = diff
            row.cost_difference_base = cost
            row.unit_cost_base = (cost / diff) if diff else unit_cost
            if diff > 0:
                surplus_items += 1
                surplus_cost += cost
            elif diff < 0:
                shortage_items += 1
                shortage_cost += -cost
        for row in rows:
            row.unit_cost_base = row.unit_cost_base.quantize(Decimal("0.000001"))
        StockCountItem.objects.bulk_update(
            rows, ["expected_quantity", "difference", "cost_difference_base", "unit_cost_base"]
        )
        count.status = StockCount.Status.COMPLETED
        count.completed_by = actor
        count.completed_at = timezone.now()
        count.surplus_cost_base = surplus_cost
        count.shortage_cost_base = shortage_cost
        count.save()
        events.StockCountCompleted.publish_from(
            actor=actor,
            branch_id=count.branch_id,
            count_id=count.pk,
            number=count.number,
            items_counted=len(rows),
            surplus_items=surplus_items,
            shortage_items=shortage_items,
            surplus_cost_base=surplus_cost,
            shortage_cost_base=shortage_cost,
        )
    return count


def cancel_count(*, actor, count: StockCount) -> StockCount:
    """Faqat yakunlanmagan inventarizatsiya (qoldiqqa hali ta'sir qilmagan)."""
    ensure_branch_access(actor, count.branch_id)
    with transaction.atomic():
        count = _locked_draft(count)
        count.status = StockCount.Status.CANCELLED
        count.cancelled_by = actor
        count.cancelled_at = timezone.now()
        count.save()
        events.StockCountCancelled.publish_from(
            actor=actor, branch_id=count.branch_id, count_id=count.pk, number=count.number
        )
    return count
