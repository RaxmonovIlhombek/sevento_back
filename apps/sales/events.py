from dataclasses import dataclass, field
from decimal import Decimal

from core.events import Event


@dataclass(frozen=True, kw_only=True)
class SaleCompleted(Event):
    name = "sale.completed"
    aggregate_type = "sale"
    aggregate_id_field = "sale_id"

    sale_id: int
    number: str
    seller_id: int
    currency: str
    total: Decimal
    total_base: Decimal
    cost_base: Decimal
    discount_total: Decimal
    items_count: int
    # [{method, currency, amount}]
    payments: list[dict] = field(default_factory=list)
    customer_id: int | None = None
    debt_amount: Decimal = Decimal(0)


@dataclass(frozen=True, kw_only=True)
class SaleCancelled(Event):
    name = "sale.cancelled"
    aggregate_type = "sale"
    aggregate_id_field = "sale_id"

    sale_id: int
    number: str
    total: Decimal
    currency: str
    reason: str


@dataclass(frozen=True, kw_only=True)
class SaleReturnCompleted(Event):
    """Qaytarish: tovar omborga, summa — qarzdan ayirildi va/yoki pul qaytarildi."""

    name = "sale_return.completed"
    aggregate_type = "sale_return"
    aggregate_id_field = "return_id"

    return_id: int
    number: str
    sale_id: int
    sale_number: str
    currency: str
    total: Decimal
    total_base: Decimal
    cost_base: Decimal
    debt_reduction: Decimal
    refund_amount: Decimal
    items_count: int
    customer_id: int | None = None
    reason: str = ""
