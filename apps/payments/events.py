from dataclasses import dataclass, field
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


@dataclass(frozen=True, kw_only=True)
class PaymentRefunded(Event):
    name = "payment.refunded"
    aggregate_type = "payment"
    aggregate_id_field = "payment_id"

    payment_id: int
    original_payment_id: int
    number: str
    method: str
    currency: str
    amount: Decimal
    is_cash: bool
    cashbox_id: int | None
    document_type: str
    document_id: int
    reason: str


@dataclass(frozen=True, kw_only=True)
class PaymentMethodSaved(Event):
    name = "payment_method.saved"
    aggregate_type = "payment_method"
    aggregate_id_field = "payment_method_id"

    payment_method_id: int
    code: str
    created: bool
    changes: dict[str, Any] = field(default_factory=dict)
