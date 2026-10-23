from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from core.events import Event


@dataclass(frozen=True, kw_only=True)
class PaymentReceived(Event):
    """Mijozdan to'lov (savdo paytida; 6-bosqichdan qarz to'lovi ham)."""

    name = "payment.received"
    aggregate_type = "payment"
    aggregate_id_field = "payment_id"

    payment_id: int
    number: str
    method: str
    currency: str
    amount: Decimal
    amount_base: Decimal
    is_cash: bool
    cashbox_id: int | None
    document_type: str
    document_id: int
    document_number: str
    customer_id: int | None = None
    # qarz to'lovi: [{debt_id, amount, currency}]
    allocated: list[dict] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class PaymentRefunded(Event):
    name = "payment.refunded"
    aggregate_type = "payment"
    aggregate_id_field = "payment_id"

    payment_id: int
    original_payment_id: int | None  # tovar qaytarishda — asl to'lovsiz
    number: str
    method: str
    currency: str
    amount: Decimal
    is_cash: bool
    cashbox_id: int | None
    document_type: str
    document_id: int
    reason: str
    customer_id: int | None = None


@dataclass(frozen=True, kw_only=True)
class PaymentMethodSaved(Event):
    name = "payment_method.saved"
    aggregate_type = "payment_method"
    aggregate_id_field = "payment_method_id"

    payment_method_id: int
    code: str
    created: bool
    changes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, kw_only=True)
class CustomerSaved(Event):
    name = "customer.saved"
    aggregate_type = "customer"
    aggregate_id_field = "customer_id"

    customer_id: int
    customer_name: str
    created: bool
    changes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, kw_only=True)
class DebtRegistered(Event):
    name = "debt.registered"
    aggregate_type = "debt"
    aggregate_id_field = "debt_id"

    debt_id: int
    customer_id: int
    amount: Decimal
    currency: str
    due_date: date
    document_type: str
    document_id: int
    document_number: str


@dataclass(frozen=True, kw_only=True)
class DebtReduced(Event):
    """Qaytarilgan tovar summasi qarzdan ayirildi."""

    name = "debt.reduced"
    aggregate_type = "debt"
    aggregate_id_field = "debt_id"

    debt_id: int
    customer_id: int
    amount: Decimal
    currency: str
    remaining: Decimal
    document_type: str
    document_id: int
    document_number: str = ""


@dataclass(frozen=True, kw_only=True)
class DebtSettled(Event):
    name = "debt.settled"
    aggregate_type = "debt"
    aggregate_id_field = "debt_id"

    debt_id: int
    customer_id: int


@dataclass(frozen=True, kw_only=True)
class DebtCancelled(Event):
    name = "debt.cancelled"
    aggregate_type = "debt"
    aggregate_id_field = "debt_id"

    debt_id: int
    customer_id: int
    amount: Decimal
    currency: str
    reason: str


@dataclass(frozen=True, kw_only=True)
class DebtOverdue(Event):
    """Celery muddati o'tganini aniqladi — har qarz uchun bir marta."""

    name = "debt.overdue"
    aggregate_type = "debt"
    aggregate_id_field = "debt_id"

    debt_id: int
    customer_id: int
    customer_name: str
    amount_remaining: Decimal
    currency: str
    due_date: date
    days_overdue: int


@dataclass(frozen=True, kw_only=True)
class CustomerCreditLimitWarning(Event):
    """Qarz limitning N% dan oshdi (chegaradan o'tish paytida bir marta)."""

    name = "customer.credit_limit_warning"
    aggregate_type = "customer"
    aggregate_id_field = "customer_id"

    customer_id: int
    customer_name: str
    used_base: Decimal
    limit_base: Decimal
    percent: Decimal
    base_currency: str


@dataclass(frozen=True, kw_only=True)
class CashShiftOpened(Event):
    name = "cash_shift.opened"
    aggregate_type = "cash_shift"
    aggregate_id_field = "shift_id"

    shift_id: int
    # [{currency, opening}]
    balances: list[dict] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class CashShiftClosed(Event):
    name = "cash_shift.closed"
    aggregate_type = "cash_shift"
    aggregate_id_field = "shift_id"

    shift_id: int
    # [{currency, opening, expected, actual, difference}]
    balances: list[dict] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class CashEntryCreated(Event):
    """Kassaga qo'lda kirim/chiqim (inkassatsiya, xarajat, kiritish)."""

    name = "cash_entry.created"
    aggregate_type = "cash_transaction"
    aggregate_id_field = "transaction_id"

    transaction_id: int
    cashbox_id: int
    currency: str
    direction: str
    category: str
    amount: Decimal
    note: str
