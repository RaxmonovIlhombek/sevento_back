"""Nasiya: mijoz, qarz yozish (kredit limiti bilan), qarz to'lovi (FIFO taqsimot), qaytarish,
muddati o'tgan qarzlar. Mijoz hisobi (CustomerLedgerEntry) har o'zgarishda yoziladi.

Qarz savdo valyutasida qoladi; boshqa valyutadagi to'lov to'lov paytidagi kurs bilan yopiladi.
Kredit limiti asosiy valyutada: ochiq qarzlar joriy kurs bilan o'tkazilib yig'iladi.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, ROUND_UP, Decimal

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.currency import selectors as currency_selectors
from core import settings_service
from core.access import ensure_branch_access
from core.exceptions import BusinessRuleError

from .. import events
from ..exceptions import (
    CreditLimitExceeded,
    DebtHasPayments,
    NoOpenDebts,
    PaymentExceedsDebt,
    RefundNotAllowed,
)
from ..models import Customer, CustomerLedgerEntry, Debt, DebtAllocation, Payment
from ..types import PaymentDoc, PaymentKind
from .payments import publish_payment_received, receive_payment, reverse_payment

MONEY = Decimal("0.0001")
CUSTOMER_DOC = "customer"


def _q(value: Decimal) -> Decimal:
    return Decimal(value).quantize(MONEY, rounding=ROUND_HALF_UP)


# --- mijoz ---


def save_customer(*, actor, customer: Customer | None = None, **fields) -> Customer:
    """Kredit limiti va nasiya muddatini faqat `customers.credit_limit.manage` o'zgartiradi."""
    limit_fields = {"credit_limit_base", "default_due_days"}
    with transaction.atomic():
        created = customer is None
        if created:
            touched = {k for k in limit_fields if fields.get(k) is not None}
        else:
            touched = {k for k in limit_fields & set(fields) if getattr(customer, k) != fields[k]}
        if touched and not actor.has_capability("customers.credit_limit.manage"):
            raise BusinessRuleError(
                "Kredit limitini o'zgartirish huquqi yo'q",
                code="credit_limit_forbidden",
                status_code=403,
            )
        if created:
            customer = Customer.objects.create(**fields)
            changes = {}
        else:
            changes = {}
            for name, value in fields.items():
                old = getattr(customer, name)
                if old != value:
                    changes[name] = {"old": old, "new": value}
                    setattr(customer, name, value)
            customer.save()
        if created or changes:
            events.CustomerSaved.publish_from(
                actor=actor,
                customer_id=customer.pk,
                customer_name=customer.name,
                created=created,
                changes=changes,
            )
    return customer


def credit_limit_base(customer: Customer) -> Decimal:
    if customer.credit_limit_base is not None:
        return customer.credit_limit_base
    return Decimal(settings_service.get("payments.default_credit_limit_base"))


def due_days(customer: Customer) -> int:
    if customer.default_due_days is not None:
        return customer.default_due_days
    return int(settings_service.get("payments.default_due_days"))


def open_debts_base(customer_id: int) -> Decimal:
    """Ochiq qarzlar asosiy valyutada, joriy kurs bilan."""
    total = Decimal(0)
    rows = (
        Debt.objects.filter(customer_id=customer_id, status=Debt.Status.OPEN)
        .values_list("currency__code", "amount", "paid_amount", "returned_amount")
        .order_by()
    )
    rates: dict[str, Decimal] = {}
    for code, amount, paid, returned in rows:
        if code not in rates:
            rates[code] = currency_selectors.rate_to_base(code)
        total += (amount - paid - returned) * rates[code]
    return _q(total)


@dataclass(frozen=True)
class CreditStatus:
    limit_base: Decimal
    used_base: Decimal

    @property
    def available_base(self) -> Decimal:
        return max(self.limit_base - self.used_base, Decimal(0))


def credit_status(customer: Customer) -> CreditStatus:
    return CreditStatus(
        limit_base=credit_limit_base(customer), used_base=open_debts_base(customer.pk)
    )


def _ledger(
    *,
    actor,
    customer_id: int,
    currency,
    type: str,  # noqa: A002
    amount: Decimal,
    debt: Debt | None = None,
    payment: Payment | None = None,
    doc: PaymentDoc | None = None,
) -> CustomerLedgerEntry:
    last = (
        CustomerLedgerEntry.objects.filter(customer_id=customer_id, currency=currency)
        .order_by("-id")
        .values_list("balance_after", flat=True)
        .first()
    )
    return CustomerLedgerEntry.objects.create(
        customer_id=customer_id,
        currency=currency,
        type=type,
        amount=amount,
        balance_after=(last or Decimal(0)) + amount,
        debt=debt,
        payment=payment,
        document_type=doc.type if doc else "",
        document_id=doc.id if doc else None,
        document_number=doc.number if doc else "",
        created_by=actor,
    )


# --- qarz yozish (savdo) ---


def register_debt(
    *,
    actor,
    customer: Customer,
    branch,
    currency,
    amount: Decimal,
    doc: PaymentDoc,
    due_date: date | None = None,
) -> Debt:
    """Nasiya. Limitdan oshsa 409 credit_limit_exceeded. Bitta mijoz bo'yicha ketma-ket (qulf)."""
    ensure_branch_access(actor, branch.pk)
    amount = _q(amount)
    if amount <= 0:
        raise ValueError("register_debt: amount > 0")
    with transaction.atomic():
        customer = Customer.objects.select_for_update().get(pk=customer.pk)
        if not customer.is_active:
            raise BusinessRuleError("Mijoz faol emas", code="customer_inactive")
        limit = credit_limit_base(customer)
        used_before = open_debts_base(customer.pk)
        amount_base = _q(amount * currency_selectors.rate_to_base(currency.code))
        if used_before + amount_base > limit:
            base = currency_selectors.base_currency_code()
            available = max(limit - used_before, Decimal(0))
            raise CreditLimitExceeded(
                f"Kredit limiti yetarli emas: mavjud {available.normalize():f} {base}, "
                f"kerak {amount_base.normalize():f} {base}",
                details=[
                    {"field": "limit_base", "code": "limit", "message": f"{limit}"},
                    {"field": "used_base", "code": "used", "message": f"{used_before}"},
                    {"field": "requested_base", "code": "requested", "message": f"{amount_base}"},
                ],
            )
        debt = Debt.objects.create(
            customer=customer,
            branch=branch,
            currency=currency,
            amount=amount,
            due_date=due_date or (timezone.localdate() + timedelta(days=due_days(customer))),
            document_type=doc.type,
            document_id=doc.id,
            document_number=doc.number,
            created_by=actor,
        )
        _ledger(
            actor=actor,
            customer_id=customer.pk,
            currency=currency,
            type=CustomerLedgerEntry.Type.DEBT,
            amount=amount,
            debt=debt,
            doc=doc,
        )
        events.DebtRegistered.publish_from(
            actor=actor,
            branch_id=branch.pk,
            debt_id=debt.pk,
            customer_id=customer.pk,
            amount=amount,
            currency=currency.code,
            due_date=debt.due_date,
            document_type=doc.type,
            document_id=doc.id,
            document_number=doc.number,
        )
        _maybe_warn(actor, customer, branch.pk, limit, used_before, used_before + amount_base)
    return debt


def _maybe_warn(actor, customer, branch_id, limit, before, after) -> None:
    if limit <= 0:
        return
    percent = Decimal(settings_service.get("payments.credit_limit_warning_percent"))
    threshold = limit * percent / 100
    if before < threshold <= after:
        events.CustomerCreditLimitWarning.publish_from(
            actor=actor,
            branch_id=branch_id,
            customer_id=customer.pk,
            customer_name=customer.name,
            used_base=after,
            limit_base=limit,
            percent=_q(after * 100 / limit).quantize(Decimal("0.1")),
            base_currency=currency_selectors.base_currency_code(),
        )


def cancel_document_debts(*, actor, doc: PaymentDoc, reason: str) -> list[Debt]:
    """Savdo bekor qilinganda uning qarzi bekor qilinadi (to'lov qilinmagan bo'lsagina)."""
    with transaction.atomic():
        debts = list(
            Debt.objects.select_for_update(of=("self",))
            .select_related("currency")
            .filter(document_type=doc.type, document_id=doc.id)
            .exclude(status=Debt.Status.CANCELLED)
            .order_by("id")
        )
        if any(d.paid_amount > 0 for d in debts):
            raise DebtHasPayments()
        for debt in debts:
            debt.status = Debt.Status.CANCELLED
            debt.save(update_fields=["status"])
            _ledger(
                actor=actor,
                customer_id=debt.customer_id,
                currency=debt.currency,
                type=CustomerLedgerEntry.Type.CANCEL,
                amount=-debt.remaining,
                debt=debt,
                doc=doc,
            )
            events.DebtCancelled.publish_from(
                actor=actor,
                branch_id=debt.branch_id,
                debt_id=debt.pk,
                customer_id=debt.customer_id,
                amount=debt.amount,
                currency=debt.currency.code,
                reason=reason,
            )
    return debts


def reduce_document_debt(*, actor, doc: PaymentDoc, currency, amount: Decimal) -> Decimal:
    """Tovar qaytarilganda hujjat (savdo) qarzi shu summaga kamayadi (qoldiqdan oshmaydi).

    Qaytaradi: qarzdan ayirilgan summa (`currency` da) — qolgani mijozga pul bilan qaytariladi.
    """
    amount = _q(amount)
    reduced = Decimal(0)
    with transaction.atomic():
        debts = list(
            Debt.objects.select_for_update(of=("self",))
            .select_related("currency")
            .filter(document_type=doc.type, document_id=doc.id, status=Debt.Status.OPEN)
            .order_by("id")
        )
        now = timezone.now()
        for debt in debts:
            left = amount - reduced
            if left <= 0:
                break
            take = min(_convert(left, currency.code, debt.currency.code), debt.remaining)
            if take <= 0:
                continue
            debt.returned_amount += take
            fields = ["returned_amount"]
            if debt.remaining <= 0:
                debt.status = Debt.Status.PAID
                debt.settled_at = now
                fields += ["status", "settled_at"]
            debt.save(update_fields=fields)
            _ledger(
                actor=actor,
                customer_id=debt.customer_id,
                currency=debt.currency,
                type=CustomerLedgerEntry.Type.RETURN,
                amount=-take,
                debt=debt,
                doc=doc,
            )
            events.DebtReduced.publish_from(
                actor=actor,
                branch_id=debt.branch_id,
                debt_id=debt.pk,
                customer_id=debt.customer_id,
                amount=take,
                currency=debt.currency.code,
                remaining=debt.remaining,
                document_type=doc.type,
                document_id=doc.id,
                document_number=doc.number,
            )
            if debt.status == Debt.Status.PAID:
                events.DebtSettled.publish_from(
                    actor=actor,
                    branch_id=debt.branch_id,
                    debt_id=debt.pk,
                    customer_id=debt.customer_id,
                )
            reduced += _convert(take, debt.currency.code, currency.code)
    return min(reduced, amount)


# --- qarz to'lovi ---


def _convert(amount: Decimal, from_code: str, to_code: str) -> Decimal:
    if from_code == to_code:
        return amount
    return _q(
        amount * currency_selectors.rate_value(from_code) / currency_selectors.rate_value(to_code)
    )


def payoff_amount(customer: Customer, currency, debt_ids: list[int] | None = None) -> Decimal:
    """Ochiq qarzlarni shu valyutada to'liq yopish uchun summa (eng kichik birlikka yuqoriga)."""
    qs = Debt.objects.filter(customer=customer, status=Debt.Status.OPEN).select_related("currency")
    if debt_ids:
        qs = qs.filter(pk__in=debt_ids)
    total = sum((_convert(d.remaining, d.currency.code, currency.code) for d in qs), Decimal(0))
    return total.quantize(Decimal(1).scaleb(-currency.decimal_places), rounding=ROUND_UP)


def receive_debt_payment(
    *,
    actor,
    customer: Customer,
    branch,
    method,
    currency,
    amount: Decimal,
    debt_ids: list[int] | None = None,
    note: str = "",
) -> Payment:
    """Qarz to'lovi: eng eski muddatdan boshlab yopiladi (yoki tanlangan qarzlar).

    Qarzdan ortiq summa qabul qilinmaydi (400 payment_exceeds_debt); to'lov valyutasining
    bitta eng kichik birligidan kam yaxlitlash qoldig'i e'tiborsiz.
    """
    ensure_branch_access(actor, branch.pk)
    amount = _q(amount)
    with transaction.atomic():
        customer = Customer.objects.select_for_update().get(pk=customer.pk)
        qs = (
            Debt.objects.select_for_update(of=("self",))
            .select_related("currency")
            .filter(customer=customer, status=Debt.Status.OPEN)
            .order_by("due_date", "id")
        )
        if debt_ids:
            qs = qs.filter(pk__in=debt_ids)
        debts = list(qs)
        if not debts:
            raise NoOpenDebts()

        pay_code = currency.code
        left = amount
        plan: list[
            tuple[Debt, Decimal, Decimal]
        ] = []  # (qarz, qarz valyutasida, to'lov valyutasida)
        for debt in debts:
            if left <= 0:
                break
            can = _convert(left, pay_code, debt.currency.code)
            take = min(can, debt.remaining)
            if take <= 0:
                continue
            consumed = (
                left if take == can else min(_convert(take, debt.currency.code, pay_code), left)
            )
            plan.append((debt, take, consumed))
            left -= consumed
        dust = Decimal(1).scaleb(-currency.decimal_places)
        if left >= dust:
            total_in_pay = sum(
                (_convert(d.remaining, d.currency.code, pay_code) for d in debts), Decimal(0)
            )
            raise PaymentExceedsDebt(
                f"Qarz jami {total_in_pay.normalize():f} {pay_code} — ortiq summa qabul qilinmaydi",
                details=[
                    {"field": "amount", "code": "max", "message": f"{total_in_pay.normalize():f}"}
                ],
            )

        doc = PaymentDoc(type=CUSTOMER_DOC, id=customer.pk, number=customer.name[:40])
        payment = receive_payment(
            actor=actor,
            branch=branch,
            method=method,
            currency=currency,
            amount=amount,
            doc=doc,
            category="debt_payment",
            customer=customer,
            note=note,
            publish=False,
        )
        now = timezone.now()
        allocated = []
        for debt, take, consumed in plan:
            DebtAllocation.objects.create(
                payment=payment, debt=debt, amount=take, payment_amount=consumed
            )
            debt.paid_amount += take
            fields = ["paid_amount"]
            if debt.remaining <= 0:
                debt.status = Debt.Status.PAID
                debt.settled_at = now
                fields += ["status", "settled_at"]
            debt.save(update_fields=fields)
            _ledger(
                actor=actor,
                customer_id=customer.pk,
                currency=debt.currency,
                type=CustomerLedgerEntry.Type.PAYMENT,
                amount=-take,
                debt=debt,
                payment=payment,
                doc=PaymentDoc(
                    type=debt.document_type, id=debt.document_id, number=debt.document_number
                ),
            )
            allocated.append(
                {"debt_id": debt.pk, "amount": str(take), "currency": debt.currency.code}
            )
            if debt.status == Debt.Status.PAID:
                events.DebtSettled.publish_from(
                    actor=actor, branch_id=debt.branch_id, debt_id=debt.pk, customer_id=customer.pk
                )
        publish_payment_received(actor, payment, allocated)
    return payment


def refund_debt_payment(*, actor, payment: Payment, reason: str) -> Payment:
    """Qarz to'lovini qaytarish (xato kiritilgan): qarzlar qayta ochiladi, naqd — kassadan."""
    ensure_branch_access(actor, payment.branch_id)
    with transaction.atomic():
        payment = (
            Payment.objects.select_for_update(of=("self",))
            .select_related("method", "currency", "branch", "customer")
            .get(pk=payment.pk)
        )
        if (
            payment.kind != PaymentKind.PAYMENT
            or payment.document_type != CUSTOMER_DOC
            or payment.status != Payment.Status.COMPLETED
        ):
            raise RefundNotAllowed(
                "Faqat qarz to'lovini qaytarish mumkin (savdo to'lovi — savdoni bekor qilib)"
            )
        allocations = payment.allocations.select_related("debt", "debt__currency")
        for alloc in allocations.select_for_update(of=("self", "debt")):
            debt = alloc.debt
            Debt.objects.filter(pk=debt.pk).update(
                paid_amount=F("paid_amount") - alloc.amount,
                status=Debt.Status.OPEN,
                settled_at=None,
            )
            _ledger(
                actor=actor,
                customer_id=payment.customer_id,
                currency=debt.currency,
                type=CustomerLedgerEntry.Type.REFUND,
                amount=alloc.amount,
                debt=debt,
                payment=payment,
                doc=PaymentDoc(
                    type=debt.document_type, id=debt.document_id, number=debt.document_number
                ),
            )
        doc = PaymentDoc(
            type=payment.document_type, id=payment.document_id, number=payment.document_number
        )
        return reverse_payment(actor=actor, original=payment, doc=doc, reason=reason)


# --- muddati o'tgan qarzlar (Celery Beat) ---


def detect_overdue_debts(today: date | None = None) -> int:
    """Muddati o'tgan ochiq qarzlar — har biri uchun bir marta debt.overdue hodisasi."""
    today = today or timezone.localdate()
    now = timezone.now()
    count = 0
    with transaction.atomic():
        debts = (
            Debt.objects.select_for_update(skip_locked=True, of=("self",))
            .select_related("customer", "currency")
            .filter(status=Debt.Status.OPEN, due_date__lt=today, overdue_notified_at__isnull=True)
            .order_by("due_date", "id")
        )
        for debt in debts:
            debt.overdue_notified_at = now
            debt.save(update_fields=["overdue_notified_at"])
            events.DebtOverdue.publish_from(
                branch_id=debt.branch_id,
                debt_id=debt.pk,
                customer_id=debt.customer_id,
                customer_name=debt.customer.name,
                amount_remaining=debt.remaining,
                currency=debt.currency.code,
                due_date=debt.due_date,
                days_overdue=(today - debt.due_date).days,
            )
            count += 1
    return count
