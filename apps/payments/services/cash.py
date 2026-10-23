"""Kassa smenasi va qo'lda kirim-chiqim (kiritish, inkassatsiya, xarajat)."""

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.currency import selectors as currency_selectors
from core.access import ensure_branch_access
from core.exceptions import InvalidStatusTransition

from .. import events
from ..exceptions import CategoryNotManual, ShiftAlreadyOpen
from ..models import Cashbox, CashFlowCategory, CashShift, CashShiftBalance, CashTransaction
from ..types import Direction, PaymentDoc
from .payments import _cash_move, get_or_create_cashbox

ADJUSTMENT_CATEGORY = "adjustment"


def open_shift(*, actor, branch, note: str = "") -> CashShift:
    """Smena ochish: har faol valyuta kassasining hozirgi qoldig'i qotiriladi."""
    ensure_branch_access(actor, branch.pk)
    with transaction.atomic():
        if (
            CashShift.objects.select_for_update()
            .filter(branch=branch, status=CashShift.Status.OPEN)
            .exists()
        ):
            raise ShiftAlreadyOpen()
        shift = CashShift.objects.create(
            branch=branch, opened_by=actor, opened_at=timezone.now(), note=note
        )
        balances = []
        for currency in currency_selectors.active_currencies():
            box = get_or_create_cashbox(branch.pk, currency)
            box = Cashbox.objects.select_for_update().get(pk=box.pk)
            CashShiftBalance.objects.create(shift=shift, cashbox=box, opening_balance=box.balance)
            balances.append({"currency": currency.code, "opening": str(box.balance)})
        events.CashShiftOpened.publish_from(
            actor=actor, branch_id=branch.pk, shift_id=shift.pk, balances=balances
        )
    return shift


def close_shift(
    *, actor, shift: CashShift, actual: dict[int, Decimal], note: str = ""
) -> CashShift:
    """Smena yopish: sanalgan naqd (valyuta id → summa). Farq bo'lsa kassa sanalganiga
    tenglashtiriladi ("Kassa farqi" yozuvi) — tizimdagi qoldiq doim haqiqiy pulga teng.
    Berilmagan valyuta uchun sanalgan = kutilgan."""
    ensure_branch_access(actor, shift.branch_id)
    with transaction.atomic():
        shift = CashShift.objects.select_for_update().get(pk=shift.pk)
        if shift.status != CashShift.Status.OPEN:
            raise InvalidStatusTransition("Smena allaqachon yopilgan")
        rows = {b.cashbox_id: b for b in shift.balances.select_related("cashbox__currency")}
        # smena davomida yangi valyuta kassasi paydo bo'lgan bo'lsa — ochilish qoldig'i 0
        for box in Cashbox.objects.filter(branch_id=shift.branch_id).exclude(pk__in=rows):
            rows[box.pk] = CashShiftBalance.objects.create(
                shift=shift, cashbox=box, opening_balance=Decimal(0)
            )
        doc = PaymentDoc(type="cash_shift", id=shift.pk, number=f"#{shift.pk}")
        summary = []
        for row in sorted(rows.values(), key=lambda r: r.cashbox_id):
            box = (
                Cashbox.objects.select_for_update(of=("self",))
                .select_related("currency")
                .get(pk=row.cashbox_id)
            )
            expected = box.balance
            counted = actual.get(box.currency_id, expected)
            difference = counted - expected
            if difference:
                _cash_move(
                    actor=actor,
                    branch_id=shift.branch_id,
                    currency=box.currency,
                    direction=Direction.IN if difference > 0 else Direction.OUT,
                    category_code=ADJUSTMENT_CATEGORY,
                    amount=abs(difference),
                    doc=doc,
                    note="Smena yopilishi: sanalgan va kutilgan farqi",
                )
            row.expected_balance = expected
            row.actual_balance = counted
            row.difference = difference
            row.save(update_fields=["expected_balance", "actual_balance", "difference"])
            summary.append(
                {
                    "currency": box.currency.code,
                    "opening": str(row.opening_balance),
                    "expected": str(expected),
                    "actual": str(counted),
                    "difference": str(difference),
                }
            )
        shift.status = CashShift.Status.CLOSED
        shift.closed_by = actor
        shift.closed_at = timezone.now()
        if note:
            shift.note = (f"{shift.note}\n{note}" if shift.note else note)[:255]
        shift.save(update_fields=["status", "closed_by", "closed_at", "note"])
        events.CashShiftClosed.publish_from(
            actor=actor, branch_id=shift.branch_id, shift_id=shift.pk, balances=summary
        )
    return shift


def manual_entry(
    *,
    actor,
    branch,
    currency,
    direction: str,
    category: CashFlowCategory,
    amount: Decimal,
    note: str,
) -> CashTransaction:
    """Qo'lda kassa yozuvi: faqat qo'lda kiritiladigan turlar (kiritish, inkassatsiya, xarajat)."""
    ensure_branch_access(actor, branch.pk)
    if not category.is_manual or category.direction not in (direction, "both"):
        raise CategoryNotManual()
    with transaction.atomic():
        tx = _cash_move(
            actor=actor,
            branch_id=branch.pk,
            currency=currency,
            direction=direction,
            category_code=category.code,
            amount=amount,
            note=note,
        )
        events.CashEntryCreated.publish_from(
            actor=actor,
            branch_id=branch.pk,
            transaction_id=tx.pk,
            cashbox_id=tx.cashbox_id,
            currency=currency.code,
            direction=direction,
            category=category.code,
            amount=amount,
            note=note,
        )
    return tx
