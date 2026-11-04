"""Yetkazish jarayoni holat mashinasi.

pending → packed (omborchi) → ready (operator) → on_the_way (kuryer qabul qiladi) → delivered.
Operator noto'g'ri deb topsa: packed → pending (sabab bilan). Bekor qilish — rahbar.
Har o'tish qator qulflanib (select_for_update) bajariladi: ikki kuryer bir buyurtmani ololmaydi.
"""

from django.db import transaction
from django.utils import timezone

from apps.sales.models import Sale
from core.exceptions import BusinessRuleError

from . import events
from .models import Fulfillment, FulfillmentStep

S = Fulfillment.Status


def _check_branch(actor, branch_id: int) -> None:
    ids = actor.accessible_branch_ids()
    if ids is not None and branch_id not in ids:
        raise BusinessRuleError(
            "Bu nuqta uchun ruxsat yo'q", code="branch_forbidden", status_code=403
        )


def _locked(pk: int) -> Fulfillment:
    return Fulfillment.objects.select_for_update().select_related("sale").get(pk=pk)


def _move(f: Fulfillment, *, actor, to: str, note: str = "", **fields) -> Fulfillment:
    previous = f.status
    f.status = to
    for key, value in fields.items():
        setattr(f, key, value)
    f.save()
    FulfillmentStep.objects.create(fulfillment=f, status=to, actor=actor, note=note)
    events.FulfillmentStatusChanged.publish_from(
        actor=actor,
        branch_id=f.branch_id,
        fulfillment_id=f.pk,
        sale_id=f.sale_id,
        number=f.sale.number,
        status=to,
        previous_status=previous,
        courier_id=f.courier_id,
        note=note,
    )
    return f


def _require(f: Fulfillment, allowed: tuple[str, ...], action: str) -> None:
    if f.status not in allowed:
        raise BusinessRuleError(
            f"Bu holatda ({f.get_status_display()}) '{action}' amalini bajarib bo'lmaydi",
            code="invalid_status",
        )


def create_for_sale(
    *, actor, sale: Sale, address: str = "", contact_phone: str = "", note: str = ""
) -> Fulfillment:
    _check_branch(actor, sale.branch_id)
    if sale.status != Sale.Status.COMPLETED:
        raise BusinessRuleError(
            "Faqat yakunlangan savdoni yetkazishga yuborish mumkin", code="sale_not_completed"
        )
    with transaction.atomic():
        if Fulfillment.objects.filter(sale=sale).exists():
            raise BusinessRuleError(
                "Bu savdo allaqachon yetkazish jarayonida", code="already_exists"
            )
        f = Fulfillment.objects.create(
            sale=sale,
            branch_id=sale.branch_id,
            address=address or (sale.customer.address if sale.customer_id else ""),
            contact_phone=contact_phone or (sale.customer.phone if sale.customer_id else ""),
            note=note,
            created_by=actor,
        )
        FulfillmentStep.objects.create(fulfillment=f, status=S.PENDING, actor=actor, note=note)
        events.FulfillmentStatusChanged.publish_from(
            actor=actor,
            branch_id=f.branch_id,
            fulfillment_id=f.pk,
            sale_id=sale.pk,
            number=sale.number,
            status=S.PENDING,
            note=note,
        )
    return f


def pack(*, actor, fulfillment_id: int, note: str = "") -> Fulfillment:
    """Omborchi: "taxladim"."""
    with transaction.atomic():
        f = _locked(fulfillment_id)
        _check_branch(actor, f.branch_id)
        _require(f, (S.PENDING,), "taxladim")
        return _move(
            f,
            actor=actor,
            to=S.PACKED,
            note=note,
            packed_by=actor,
            packed_at=timezone.now(),
            reject_reason="",
        )


def verify(*, actor, fulfillment_id: int, note: str = "") -> Fulfillment:
    """Operator: tekshirdi, "tayyor"."""
    with transaction.atomic():
        f = _locked(fulfillment_id)
        _check_branch(actor, f.branch_id)
        _require(f, (S.PACKED,), "tayyor")
        return _move(
            f,
            actor=actor,
            to=S.READY,
            note=note,
            verified_by=actor,
            verified_at=timezone.now(),
        )


def reject(*, actor, fulfillment_id: int, reason: str) -> Fulfillment:
    """Operator: noto'g'ri taxlangan — omborchiga qaytaradi."""
    if not reason.strip():
        raise BusinessRuleError("Qaytarish sababini yozing", code="reason_required")
    with transaction.atomic():
        f = _locked(fulfillment_id)
        _check_branch(actor, f.branch_id)
        _require(f, (S.PACKED,), "qaytarish")
        return _move(
            f,
            actor=actor,
            to=S.PENDING,
            note=reason,
            reject_reason=reason,
            packed_by=None,
            packed_at=None,
        )


def accept(*, actor, fulfillment_id: int) -> Fulfillment:
    """Kuryer: buyurtmani qabul qildi (birinchi bosgan oladi)."""
    with transaction.atomic():
        f = _locked(fulfillment_id)
        _check_branch(actor, f.branch_id)
        _require(f, (S.READY,), "qabul qilish")
        return _move(f, actor=actor, to=S.ON_THE_WAY, courier=actor, accepted_at=timezone.now())


def deliver(*, actor, fulfillment_id: int, note: str = "") -> Fulfillment:
    """Kuryer: "yetib keldim, hammasini berdim"."""
    with transaction.atomic():
        f = _locked(fulfillment_id)
        _check_branch(actor, f.branch_id)
        _require(f, (S.ON_THE_WAY,), "yetkazildi")
        is_manager = actor.has_capability("fulfillment.manage")
        if f.courier_id != actor.pk and not is_manager:
            raise BusinessRuleError(
                "Bu buyurtma boshqa kuryerga biriktirilgan",
                code="not_your_delivery",
                status_code=403,
            )
        return _move(
            f,
            actor=actor,
            to=S.DELIVERED,
            note=note,
            delivered_at=timezone.now(),
            delivered_note=note,
        )


def cancel(*, actor, fulfillment_id: int, reason: str) -> Fulfillment:
    if not reason.strip():
        raise BusinessRuleError("Bekor qilish sababini yozing", code="reason_required")
    with transaction.atomic():
        f = _locked(fulfillment_id)
        _check_branch(actor, f.branch_id)
        _require(f, (S.PENDING, S.PACKED, S.READY, S.ON_THE_WAY), "bekor qilish")
        return _move(
            f,
            actor=actor,
            to=S.CANCELLED,
            note=reason,
            cancelled_by=actor,
            cancelled_at=timezone.now(),
            cancel_reason=reason,
        )
