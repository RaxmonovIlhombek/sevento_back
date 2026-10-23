"""Ko'chirish: qoralama → jo'natish (manbadan FIFO chiqim) → qabul qilish yoki bekor qilish.

Qabulda manzil nuqtada asl partiya tannarxi bilan yangi partiyalar yaratiladi (`parent` — manba
partiya). Qabul qilingan miqdor jo'natilgandan kam bo'lsa farq "yo'lda yo'qolgan" sifatida
avtomatik hisobdan chiqarish hujjatiga yoziladi (sabab `transfer_shortage`), rahbarga xabar ketadi.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone

from core.access import ensure_branch_access
from core.exceptions import BusinessRuleError, InvalidStatusTransition
from core.numbering import next_number

from .. import events
from ..exceptions import InsufficientStock
from ..models import Transfer, TransferItem
from ..types import (
    BatchAllocation,
    DocRef,
    MovementType,
    allocations_from_json,
    allocations_to_json,
)
from . import writeoffs
from .common import line_insufficient, precision_error, validate_lines, validation_error
from .stock import MONEY_PLACES, UNIT_COST_PLACES, issue_stock, receive_stock, restore_stock

DOC_TYPE = "transfer"
NUMBER_PREFIX = "KO"

TRANSITIONS = {
    Transfer.Status.DRAFT: {Transfer.Status.SENT, Transfer.Status.CANCELLED},
    Transfer.Status.SENT: {Transfer.Status.RECEIVED, Transfer.Status.CANCELLED},
    Transfer.Status.RECEIVED: set(),
    Transfer.Status.CANCELLED: set(),
}


def _check_transition(transfer: Transfer, target: str) -> None:
    if target not in TRANSITIONS[transfer.status]:
        raise InvalidStatusTransition(
            f"Holat «{transfer.get_status_display()}» dan o'tib bo'lmaydi"
        )


def _check_destination(from_branch_id: int, to_branch) -> None:
    if to_branch.pk == from_branch_id:
        raise validation_error(
            "Jo'natuvchi va qabul qiluvchi nuqta bir xil",
            [{"field": "to_branch", "code": "same_branch", "message": "Boshqa nuqtani tanlang"}],
        )
    if not to_branch.is_active:
        raise validation_error(
            "Qabul qiluvchi nuqta faol emas",
            [{"field": "to_branch", "code": "branch_inactive", "message": "Nuqta faol emas"}],
        )


def _write_lines(transfer: Transfer, items: list[dict]) -> None:
    validate_lines(items)
    transfer.items.all().delete()
    TransferItem.objects.bulk_create(
        [
            TransferItem(
                transfer=transfer,
                product=item["product"],
                position=index,
                quantity=item["quantity"],
            )
            for index, item in enumerate(items)
        ]
    )


def _branch_names(transfer: Transfer) -> dict:
    return {
        "from_branch_id": transfer.from_branch_id,
        "from_branch_name": transfer.from_branch.name,
        "to_branch_id": transfer.to_branch_id,
        "to_branch_name": transfer.to_branch.name,
    }


def _locked(transfer: Transfer) -> Transfer:
    return (
        Transfer.objects.select_for_update(of=("self",))
        .select_related("from_branch", "to_branch")
        .get(pk=transfer.pk)
    )


def create_transfer(
    *, actor, from_branch, to_branch, items: list[dict], note: str = ""
) -> Transfer:
    ensure_branch_access(actor, from_branch.pk)
    _check_destination(from_branch.pk, to_branch)
    with transaction.atomic():
        transfer = Transfer.objects.create(
            number=next_number(
                doc_type=NUMBER_PREFIX, branch_id=from_branch.pk, branch_code=from_branch.code
            ),
            from_branch=from_branch,
            to_branch=to_branch,
            note=note,
            created_by=actor,
        )
        _write_lines(transfer, items)
        events.TransferCreated.publish_from(
            actor=actor,
            branch_id=from_branch.pk,
            transfer_id=transfer.pk,
            number=transfer.number,
            from_branch_id=from_branch.pk,
            to_branch_id=to_branch.pk,
        )
    return transfer


def update_transfer(
    *, actor, transfer: Transfer, items: list[dict] | None = None, **fields
) -> Transfer:
    """Faqat qoralama. Jo'natuvchi nuqta o'zgarmaydi (raqam unga bog'langan)."""
    ensure_branch_access(actor, transfer.from_branch_id)
    with transaction.atomic():
        transfer = _locked(transfer)
        if transfer.status != Transfer.Status.DRAFT:
            raise InvalidStatusTransition("Faqat qoralamani tahrirlash mumkin")
        from_branch = fields.pop("from_branch", None)
        if from_branch is not None and from_branch.pk != transfer.from_branch_id:
            raise BusinessRuleError(
                "Jo'natuvchi nuqtani o'zgartirib bo'lmaydi (raqam nuqtaga bog'langan)",
                code="branch_locked",
            )
        if "to_branch" in fields:
            _check_destination(transfer.from_branch_id, fields["to_branch"])
        for name, value in fields.items():
            setattr(transfer, name, value)
        transfer.save()
        if items is not None:
            _write_lines(transfer, items)
    return transfer


def send_transfer(*, actor, transfer: Transfer) -> Transfer:
    """Jo'natish: manba nuqtadan FIFO chiqim; partiyalar qatorga yoziladi (bekor/qabul uchun)."""
    ensure_branch_access(actor, transfer.from_branch_id)
    with transaction.atomic():
        transfer = _locked(transfer)
        _check_transition(transfer, Transfer.Status.SENT)
        _check_destination(transfer.from_branch_id, transfer.to_branch)
        items = list(transfer.items.select_related("product", "product__unit"))
        if not items:
            raise BusinessRuleError("Ko'chirishda tovar yo'q", code="transfer_empty")
        total = Decimal(0)
        # qulflar doim tovar id tartibida — parallel hujjatlarda deadlock bo'lmasin
        for item in sorted(items, key=lambda i: (i.product_id, i.position)):
            try:
                result = issue_stock(
                    actor=actor,
                    branch_id=transfer.from_branch_id,
                    product_id=item.product_id,
                    quantity=item.quantity,
                    movement_type=MovementType.TRANSFER_OUT,
                    doc=DocRef(
                        type=DOC_TYPE, id=transfer.pk, number=transfer.number, line_id=item.pk
                    ),
                )
            except InsufficientStock as exc:
                raise line_insufficient(exc, item.product.name, item.position) from None
            item.batch_allocations = allocations_to_json(result.allocations)
            item.total_cost_base = result.total_cost_base
            item.unit_cost_base = result.unit_cost_base.quantize(UNIT_COST_PLACES, ROUND_HALF_UP)
            total += result.total_cost_base
        TransferItem.objects.bulk_update(
            items, ["batch_allocations", "total_cost_base", "unit_cost_base"]
        )
        transfer.status = Transfer.Status.SENT
        transfer.sent_by = actor
        transfer.sent_at = timezone.now()
        transfer.total_cost_base = total
        transfer.save()
        events.TransferSent.publish_from(
            actor=actor,
            branch_id=transfer.from_branch_id,
            transfer_id=transfer.pk,
            number=transfer.number,
            items_count=len(items),
            total_cost_base=total,
            **_branch_names(transfer),
        )
    return transfer


def _received_quantities(items: list[TransferItem], received: dict[int, Decimal] | None) -> None:
    """Qabul qilingan miqdorlar (berilmagan qator — to'liq). 0 ≤ qabul ≤ jo'natilgan."""
    received = received or {}
    unknown = set(received) - {i.pk for i in items}
    if unknown:
        raise validation_error(
            "Ko'chirishda bunday qator yo'q",
            [{"field": "items", "code": "unknown_item", "message": str(sorted(unknown))}],
        )
    errors = []
    for item in items:
        qty = received.get(item.pk, item.quantity)
        field = f"items.{item.position}.quantity_received"
        if qty < 0 or qty > item.quantity:
            errors.append(
                {
                    "field": field,
                    "code": "received_out_of_range",
                    "message": f"0 dan {item.quantity.normalize():f} gacha",
                }
            )
            continue
        error = precision_error(item.product, qty, field)
        if error:
            errors.append(error)
        item.quantity_received = qty
    if errors:
        raise validation_error("Qabul qilingan miqdorlarda xato bor", errors)


def _split(allocations: list[BatchAllocation], received: Decimal):
    """FIFO tartibida: avval qabul qilingan qism, qolgani — yo'qolgan."""
    got, lost = [], []
    left = received
    for alloc in allocations:
        take = min(alloc.quantity, left)
        left -= take
        if take > 0:
            got.append(BatchAllocation(alloc.batch_id, take, alloc.unit_cost_base))
        if alloc.quantity - take > 0:
            lost.append(
                BatchAllocation(alloc.batch_id, alloc.quantity - take, alloc.unit_cost_base)
            )
    return got, lost


def receive_transfer(
    *, actor, transfer: Transfer, received: dict[int, Decimal] | None = None, note: str = ""
) -> Transfer:
    """Qabul: manzilda asl tannarxli partiyalar; yetishmagan qism — avtomatik hisobdan chiqarish."""
    ensure_branch_access(actor, transfer.to_branch_id)
    with transaction.atomic():
        transfer = _locked(transfer)
        _check_transition(transfer, Transfer.Status.RECEIVED)
        items = list(transfer.items.select_related("product", "product__unit"))
        _received_quantities(items, received)
        now = timezone.now()
        shortages: list[tuple[TransferItem, list[BatchAllocation]]] = []
        for item in sorted(items, key=lambda i: (i.product_id, i.position)):
            got, lost = _split(
                allocations_from_json(item.batch_allocations), item.quantity_received
            )
            doc = DocRef(type=DOC_TYPE, id=transfer.pk, number=transfer.number, line_id=item.pk)
            for alloc in got:
                receive_stock(
                    actor=actor,
                    branch_id=transfer.to_branch_id,
                    product_id=item.product_id,
                    quantity=alloc.quantity,
                    unit_cost_base=alloc.unit_cost_base,
                    movement_type=MovementType.TRANSFER_IN,
                    doc=doc,
                    received_at=now,
                    parent_batch_id=alloc.batch_id,
                )
            if lost:
                shortages.append((item, lost))
        TransferItem.objects.bulk_update(items, ["quantity_received"])

        shortage_cost = Decimal(0)
        if shortages:
            write_off = writeoffs.record_transfer_shortage(
                actor=actor, transfer=transfer, lines=shortages
            )
            shortage_cost = write_off.total_cost_base
        transfer.status = Transfer.Status.RECEIVED
        transfer.received_by = actor
        transfer.received_at = now
        transfer.receive_note = note
        transfer.has_discrepancy = bool(shortages)
        transfer.shortage_cost_base = shortage_cost.quantize(MONEY_PLACES)
        transfer.save()
        events.TransferReceived.publish_from(
            actor=actor,
            branch_id=transfer.to_branch_id,
            transfer_id=transfer.pk,
            number=transfer.number,
            has_discrepancy=transfer.has_discrepancy,
            shortage_cost_base=transfer.shortage_cost_base,
            discrepancies=[
                {
                    "product_id": item.product_id,
                    "product_name": item.product.name,
                    "quantity": str(item.quantity),
                    "quantity_received": str(item.quantity_received),
                }
                for item, _ in shortages
            ],
            **_branch_names(transfer),
        )
    return transfer


def cancel_transfer(*, actor, transfer: Transfer, reason: str) -> Transfer:
    """Qoralama — shunchaki bekor. Jo'natilgan — tovar manbadagi asl partiyalarga qaytadi."""
    ensure_branch_access(actor, transfer.from_branch_id)
    with transaction.atomic():
        transfer = _locked(transfer)
        _check_transition(transfer, Transfer.Status.CANCELLED)
        previous = transfer.status
        if previous == Transfer.Status.SENT:
            items = transfer.items.all()
            for item in sorted(items, key=lambda i: (i.product_id, i.position)):
                restore_stock(
                    actor=actor,
                    branch_id=transfer.from_branch_id,
                    product_id=item.product_id,
                    allocations=allocations_from_json(item.batch_allocations),
                    movement_type=MovementType.TRANSFER_CANCEL,
                    doc=DocRef(
                        type=DOC_TYPE, id=transfer.pk, number=transfer.number, line_id=item.pk
                    ),
                )
        transfer.status = Transfer.Status.CANCELLED
        transfer.cancelled_by = actor
        transfer.cancelled_at = timezone.now()
        transfer.cancel_reason = reason
        transfer.save()
        events.TransferCancelled.publish_from(
            actor=actor,
            branch_id=transfer.from_branch_id,
            transfer_id=transfer.pk,
            number=transfer.number,
            previous_status=previous,
            reason=reason,
            **_branch_names(transfer),
        )
    return transfer
