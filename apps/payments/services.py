"""Pul harakatining yagona joyi: to'lov, qaytim, qaytarish va kassa jurnali.

Boshqa app lar (sales, keyin qarzlar) Payment/Cashbox ga to'g'ridan-to'g'ri yozmaydi — faqat shu
funksiyalar orqali. Hammasi chaqiruvchining tranzaksiyasi ichida ishlaydi.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone

from apps.branches import selectors as branch_selectors
from apps.currency import selectors as currency_selectors
from core.access import ensure_branch_access
from core.exceptions import BusinessRuleError
from core.numbering import next_number

from . import events, selectors
from .exceptions import InsufficientCash, NoCashMethod, PaymentDeclined
from .models import Cashbox, CashFlowCategory, CashTransaction, Payment, PaymentMethod
from .providers import get_provider
from .types import Direction, PaymentDoc, PaymentKind

MONEY_PLACES = Decimal("0.0001")
NUMBER_PREFIX = "T"


def _changes(instance, fields: dict) -> dict:
    changes = {}
    for name, value in fields.items():
        old = getattr(instance, name)
        if old != value:
            changes[name] = {"old": old, "new": value}
            setattr(instance, name, value)
    return changes


def save_payment_method(*, actor, method: PaymentMethod | None = None, **fields) -> PaymentMethod:
    if "provider" in fields:
        get_provider(fields["provider"])  # noma'lum provayder → 409 provider_unavailable
    with transaction.atomic():
        created = method is None
        if created:
            method = PaymentMethod.objects.create(**fields)
            changes = {}
        else:
            changes = _changes(method, fields)
            method.save()
        if created or changes:
            events.PaymentMethodSaved.publish_from(
                actor=actor,
                payment_method_id=method.pk,
                code=method.code,
                created=created,
                changes=changes,
            )
    return method


# --- kassa ---


def get_or_create_cashbox(branch_id: int, currency) -> Cashbox:
    cashbox = Cashbox.objects.filter(branch_id=branch_id, currency=currency).first()
    if cashbox is not None:
        return cashbox
    branch = branch_selectors.get_branch(branch_id)
    cashbox, _ = Cashbox.objects.get_or_create(
        branch_id=branch_id,
        currency=currency,
        defaults={"name": f"{branch.code if branch else branch_id} · {currency.code}"},
    )
    return cashbox


def _cash_move(
    *,
    actor,
    branch_id: int,
    currency,
    direction: str,
    category_code: str,
    amount: Decimal,
    payment: Payment | None = None,
    doc: PaymentDoc | None = None,
    note: str = "",
) -> CashTransaction:
    cashbox = get_or_create_cashbox(branch_id, currency)
    cashbox = Cashbox.objects.select_for_update().get(pk=cashbox.pk)
    if direction == Direction.OUT:
        if cashbox.balance < amount:
            raise InsufficientCash(
                details=[
                    {
                        "field": "amount",
                        "code": "insufficient_cash",
                        "message": f"Kassada: {cashbox.balance.normalize():f} {currency.code}",
                    }
                ]
            )
        cashbox.balance -= amount
    else:
        cashbox.balance += amount
    cashbox.save(update_fields=["balance", "updated_at"])
    return CashTransaction.objects.create(
        cashbox=cashbox,
        direction=direction,
        category=CashFlowCategory.objects.get(code=category_code),
        amount=amount,
        balance_after=cashbox.balance,
        payment=payment,
        document_type=doc.type if doc else "",
        document_id=doc.id if doc else None,
        document_number=doc.number if doc else "",
        note=note,
        created_by=actor,
    )


# --- to'lovlar ---


def _create_payment(
    *,
    actor,
    branch,
    method: PaymentMethod,
    kind: str,
    direction: str,
    currency,
    amount: Decimal,
    doc: PaymentDoc,
    rate_to_base: Decimal | None = None,
    reversal_of: Payment | None = None,
    provider_reference: str = "",
    note: str = "",
) -> Payment:
    amount = Decimal(amount).quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)
    if amount <= 0:
        raise BusinessRuleError(
            "Summa musbat bo'lishi kerak", code="invalid_amount", status_code=400
        )
    rate = (
        rate_to_base if rate_to_base is not None else currency_selectors.rate_to_base(currency.code)
    )
    return Payment.objects.create(
        number=next_number(doc_type=NUMBER_PREFIX, branch_id=branch.pk, branch_code=branch.code),
        branch=branch,
        method=method,
        kind=kind,
        direction=direction,
        currency=currency,
        amount=amount,
        rate_to_base=rate,
        amount_base=(amount * rate).quantize(MONEY_PLACES, rounding=ROUND_HALF_UP),
        reversal_of=reversal_of,
        provider_reference=provider_reference,
        document_type=doc.type,
        document_id=doc.id,
        document_number=doc.number,
        received_by=actor,
        received_at=timezone.now(),
        note=note,
    )


def receive_payment(
    *,
    actor,
    branch,
    method: PaymentMethod,
    currency,
    amount: Decimal,
    doc: PaymentDoc,
    category: str = "sale",
    note: str = "",
) -> Payment:
    """Mijozdan pul: provayder (naqd — darhol), to'lov yozuvi, naqd bo'lsa kassaga kirim."""
    ensure_branch_access(actor, branch.pk)
    if not method.is_active:
        raise BusinessRuleError(f"«{method.name}» to'lov turi faol emas", code="method_inactive")
    with transaction.atomic():
        result = get_provider(method.provider).charge(
            amount=amount, currency_code=currency.code, reference=doc.number
        )
        if not result.ok:
            raise PaymentDeclined(result.message or None)
        payment = _create_payment(
            actor=actor,
            branch=branch,
            method=method,
            kind=PaymentKind.PAYMENT,
            direction=Direction.IN,
            currency=currency,
            amount=amount,
            doc=doc,
            provider_reference=result.reference,
            note=note,
        )
        cashbox_id = None
        if method.is_cash:
            tx = _cash_move(
                actor=actor,
                branch_id=branch.pk,
                currency=currency,
                direction=Direction.IN,
                category_code=category,
                amount=payment.amount,
                payment=payment,
                doc=doc,
            )
            cashbox_id = tx.cashbox_id
        events.PaymentReceived.publish_from(
            actor=actor,
            branch_id=branch.pk,
            payment_id=payment.pk,
            number=payment.number,
            method=method.code,
            currency=currency.code,
            amount=payment.amount,
            amount_base=payment.amount_base,
            is_cash=method.is_cash,
            cashbox_id=cashbox_id,
            document_type=doc.type,
            document_id=doc.id,
            document_number=doc.number,
        )
    return payment


def give_change(
    *, actor, branch, currency, amount: Decimal, doc: PaymentDoc, category: str = "sale"
) -> Payment:
    """Qaytim — har doim naqd, kassadan chiqim (kassada yetmasa 409 insufficient_cash)."""
    method = selectors.cash_method()
    if method is None:
        raise NoCashMethod()
    with transaction.atomic():
        payment = _create_payment(
            actor=actor,
            branch=branch,
            method=method,
            kind=PaymentKind.CHANGE,
            direction=Direction.OUT,
            currency=currency,
            amount=amount,
            doc=doc,
        )
        _cash_move(
            actor=actor,
            branch_id=branch.pk,
            currency=currency,
            direction=Direction.OUT,
            category_code=category,
            amount=payment.amount,
            payment=payment,
            doc=doc,
        )
    return payment


MIRROR = {
    PaymentKind.PAYMENT: (PaymentKind.REFUND, Direction.OUT, "refund"),
    PaymentKind.CHANGE: (PaymentKind.CHANGE_RETURN, Direction.IN, "sale"),
}


def reverse_document_payments(*, actor, doc: PaymentDoc, reason: str) -> list[Payment]:
    """Hujjat (savdo) bekor qilinganda uning barcha to'lovlarini teskari yozadi.

    Avval qaytimlar (kassaga kirim), keyin to'lovlar (kassadan chiqim) — kassa qoldig'i
    oraliqda manfiy bo'lmasin. Asl kurs saqlanadi: asosiy valyutadagi summa aniq teskari.
    """
    with transaction.atomic():
        originals = list(
            Payment.objects.select_for_update()
            .select_related("method", "currency", "branch")
            .filter(
                document_type=doc.type,
                document_id=doc.id,
                status=Payment.Status.COMPLETED,
                kind__in=list(MIRROR),
            )
            .order_by("id")
        )
        originals.sort(key=lambda p: 0 if p.kind == PaymentKind.CHANGE else 1)
        mirrors = []
        for original in originals:
            kind, direction, category = MIRROR[original.kind]
            reference = ""
            if original.kind == PaymentKind.PAYMENT:
                result = get_provider(original.method.provider).refund(
                    amount=original.amount,
                    currency_code=original.currency.code,
                    original_reference=original.provider_reference,
                )
                if not result.ok:
                    raise PaymentDeclined(result.message or "Provayder pulni qaytarmadi")
                reference = result.reference
            mirror = _create_payment(
                actor=actor,
                branch=original.branch,
                method=original.method,
                kind=kind,
                direction=direction,
                currency=original.currency,
                amount=original.amount,
                doc=doc,
                rate_to_base=original.rate_to_base,
                reversal_of=original,
                provider_reference=reference,
                note=reason[:255],
            )
            original.status = Payment.Status.REVERSED
            original.save(update_fields=["status"])
            cashbox_id = None
            if original.method.is_cash:
                tx = _cash_move(
                    actor=actor,
                    branch_id=original.branch_id,
                    currency=original.currency,
                    direction=direction,
                    category_code=category,
                    amount=original.amount,
                    payment=mirror,
                    doc=doc,
                    note=reason[:255],
                )
                cashbox_id = tx.cashbox_id
            if kind == PaymentKind.REFUND:
                events.PaymentRefunded.publish_from(
                    actor=actor,
                    branch_id=original.branch_id,
                    payment_id=mirror.pk,
                    original_payment_id=original.pk,
                    number=mirror.number,
                    method=original.method.code,
                    currency=original.currency.code,
                    amount=original.amount,
                    is_cash=original.method.is_cash,
                    cashbox_id=cashbox_id,
                    document_type=doc.type,
                    document_id=doc.id,
                    reason=reason,
                )
            mirrors.append(mirror)
    return mirrors
