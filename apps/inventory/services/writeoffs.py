"""Hisobdan chiqarish: yaratilishi bilan FIFO chiqim (sabab bilan); bekor — asl partiyalarga.

Ko'chirishda yo'qolgan tovar uchun hujjat avtomatik yaratiladi (`record_transfer_shortage`):
tovar manzilga yetib kelmagan, shuning uchun qoldiq harakati yo'q — faqat yo'qotish qiymati.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone

from core.access import ensure_branch_access
from core.exceptions import InvalidStatusTransition
from core.numbering import next_number

from .. import events
from ..exceptions import InsufficientStock, SystemWriteOff
from ..models import Transfer, WriteOff, WriteOffItem, WriteOffReason
from ..types import (
    BatchAllocation,
    DocRef,
    MovementType,
    allocations_from_json,
    allocations_to_json,
)
from .common import line_insufficient, validate_lines, validation_error
from .stock import MONEY_PLACES, UNIT_COST_PLACES, issue_stock, restore_stock

DOC_TYPE = "write_off"
NUMBER_PREFIX = "HC"
TRANSFER_SHORTAGE = "transfer_shortage"


def save_reason(*, actor, reason: WriteOffReason | None = None, **fields) -> WriteOffReason:
    with transaction.atomic():
        created = reason is None
        changes = {}
        if created:
            reason = WriteOffReason.objects.create(**fields)
        else:
            for name, value in fields.items():
                old = getattr(reason, name)
                if old != value:
                    changes[name] = {"old": old, "new": value}
                    setattr(reason, name, value)
            reason.save()
        if created or changes:
            events.WriteOffReasonSaved.publish_from(
                actor=actor, reason_id=reason.pk, code=reason.code, created=created, changes=changes
            )
    return reason


def create_write_off(
    *, actor, branch, reason: WriteOffReason, items: list[dict], note: str = ""
) -> WriteOff:
    ensure_branch_access(actor, branch.pk)
    if reason.is_system or not reason.is_active:
        raise validation_error(
            "Bu sababni tanlab bo'lmaydi",
            [{"field": "reason", "code": "reason_not_allowed", "message": reason.name}],
        )
    validate_lines(items)
    with transaction.atomic():
        write_off = WriteOff.objects.create(
            number=next_number(
                doc_type=NUMBER_PREFIX, branch_id=branch.pk, branch_code=branch.code
            ),
            branch=branch,
            reason=reason,
            note=note,
            created_by=actor,
            completed_at=timezone.now(),
        )
        rows = WriteOffItem.objects.bulk_create(
            [
                WriteOffItem(
                    write_off=write_off,
                    product=item["product"],
                    position=index,
                    quantity=item["quantity"],
                )
                for index, item in enumerate(items)
            ]
        )
        products = {item["product"].pk: item["product"] for item in items}
        total = Decimal(0)
        for row in sorted(rows, key=lambda r: (r.product_id, r.position)):
            try:
                result = issue_stock(
                    actor=actor,
                    branch_id=branch.pk,
                    product_id=row.product_id,
                    quantity=row.quantity,
                    movement_type=MovementType.WRITE_OFF,
                    doc=DocRef(
                        type=DOC_TYPE, id=write_off.pk, number=write_off.number, line_id=row.pk
                    ),
                )
            except InsufficientStock as exc:
                raise line_insufficient(exc, products[row.product_id].name, row.position) from None
            row.batch_allocations = allocations_to_json(result.allocations)
            row.total_cost_base = result.total_cost_base
            row.unit_cost_base = result.unit_cost_base.quantize(UNIT_COST_PLACES, ROUND_HALF_UP)
            total += result.total_cost_base
        WriteOffItem.objects.bulk_update(
            rows, ["batch_allocations", "total_cost_base", "unit_cost_base"]
        )
        write_off.total_cost_base = total
        write_off.save(update_fields=["total_cost_base", "updated_at"])
        events.WriteOffCompleted.publish_from(
            actor=actor,
            branch_id=branch.pk,
            write_off_id=write_off.pk,
            number=write_off.number,
            reason=reason.code,
            total_cost_base=total,
            items_count=len(rows),
        )
    return write_off


def record_transfer_shortage(
    *, actor, transfer: Transfer, lines: list[tuple[object, list[BatchAllocation]]]
) -> WriteOff:
    """Ko'chirish qabulida yetishmagan tovar (qabul qiluvchi nuqtada, qoldiqqa ta'sirsiz)."""
    reason = WriteOffReason.objects.get(code=TRANSFER_SHORTAGE)
    branch = transfer.to_branch
    write_off = WriteOff.objects.create(
        number=next_number(doc_type=NUMBER_PREFIX, branch_id=branch.pk, branch_code=branch.code),
        branch=branch,
        reason=reason,
        note=f"{transfer.number}: ko'chirishda yetishmadi",
        transfer=transfer,
        created_by=actor,
        completed_at=timezone.now(),
    )
    rows = []
    total = Decimal(0)
    for index, (item, lost) in enumerate(lines):
        qty = sum((a.quantity for a in lost), Decimal(0))
        cost = sum(
            ((a.quantity * a.unit_cost_base).quantize(MONEY_PLACES, ROUND_HALF_UP) for a in lost),
            Decimal(0),
        )
        total += cost
        rows.append(
            WriteOffItem(
                write_off=write_off,
                product_id=item.product_id,
                position=index,
                quantity=qty,
                unit_cost_base=(cost / qty).quantize(UNIT_COST_PLACES, ROUND_HALF_UP),
                total_cost_base=cost,
                batch_allocations=allocations_to_json(lost),
            )
        )
    WriteOffItem.objects.bulk_create(rows)
    write_off.total_cost_base = total
    write_off.save(update_fields=["total_cost_base", "updated_at"])
    events.WriteOffCompleted.publish_from(
        actor=actor,
        branch_id=branch.pk,
        write_off_id=write_off.pk,
        number=write_off.number,
        reason=reason.code,
        total_cost_base=total,
        items_count=len(rows),
        transfer_id=transfer.pk,
    )
    return write_off


def cancel_write_off(*, actor, write_off: WriteOff, reason: str) -> WriteOff:
    """Bekor qilish: tovar asl partiyalarga qaytadi (tannarx saqlanadi)."""
    ensure_branch_access(actor, write_off.branch_id)
    with transaction.atomic():
        write_off = WriteOff.objects.select_for_update().get(pk=write_off.pk)
        if write_off.status != WriteOff.Status.COMPLETED:
            raise InvalidStatusTransition("Hujjat allaqachon bekor qilingan")
        if write_off.transfer_id is not None:
            raise SystemWriteOff()
        for row in sorted(write_off.items.all(), key=lambda r: (r.product_id, r.position)):
            restore_stock(
                actor=actor,
                branch_id=write_off.branch_id,
                product_id=row.product_id,
                allocations=allocations_from_json(row.batch_allocations),
                movement_type=MovementType.WRITE_OFF_CANCEL,
                doc=DocRef(type=DOC_TYPE, id=write_off.pk, number=write_off.number, line_id=row.pk),
            )
        write_off.status = WriteOff.Status.CANCELLED
        write_off.cancelled_by = actor
        write_off.cancelled_at = timezone.now()
        write_off.cancel_reason = reason
        write_off.save()
        events.WriteOffCancelled.publish_from(
            actor=actor,
            branch_id=write_off.branch_id,
            write_off_id=write_off.pk,
            number=write_off.number,
            total_cost_base=write_off.total_cost_base,
            reason=reason,
        )
    return write_off
