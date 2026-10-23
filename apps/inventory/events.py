from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from core.events import Event


@dataclass(frozen=True, kw_only=True)
class StockChanged(Event):
    """Har qoldiq o'zgarishi (nuqta × tovar). Auditsiz (jurnal o'zi tarix)."""

    name = "stock.changed"
    aggregate_type = "stock"
    aggregate_id_field = "product_id"
    audit = False

    product_id: int
    quantity_before: Decimal
    quantity_after: Decimal
    delta: Decimal
    movement_type: str
    document_type: str
    document_id: int
    document_number: str = ""


@dataclass(frozen=True, kw_only=True)
class StockBelowMinimum(Event):
    """Qoldiq minimaldan tushdi — faqat chegaradan o'tish paytida (har safar emas)."""

    name = "stock.below_minimum"
    aggregate_type = "stock"
    aggregate_id_field = "product_id"

    product_id: int
    product_name: str
    quantity: Decimal
    min_quantity: Decimal
    unit: str


@dataclass(frozen=True, kw_only=True)
class MinQuantityChanged(Event):
    name = "stock.min_quantity_changed"
    aggregate_type = "stock"
    aggregate_id_field = "product_id"

    product_id: int
    old_value: Decimal | None
    new_value: Decimal | None


# --- 7-bosqich: ko'chirish ---


@dataclass(frozen=True, kw_only=True)
class TransferCreated(Event):
    name = "transfer.created"
    aggregate_type = "transfer"
    aggregate_id_field = "transfer_id"

    transfer_id: int
    number: str
    from_branch_id: int
    to_branch_id: int


@dataclass(frozen=True, kw_only=True)
class TransferSent(Event):
    """Jo'natildi (manbadan chiqim). branch_id — jo'natuvchi nuqta."""

    name = "transfer.sent"
    aggregate_type = "transfer"
    aggregate_id_field = "transfer_id"

    transfer_id: int
    number: str
    from_branch_id: int
    from_branch_name: str
    to_branch_id: int
    to_branch_name: str
    items_count: int
    total_cost_base: Decimal


@dataclass(frozen=True, kw_only=True)
class TransferReceived(Event):
    """Qabul qilindi (farq bilan ham). branch_id — qabul qiluvchi nuqta."""

    name = "transfer.received"
    aggregate_type = "transfer"
    aggregate_id_field = "transfer_id"

    transfer_id: int
    number: str
    from_branch_id: int
    from_branch_name: str
    to_branch_id: int
    to_branch_name: str
    has_discrepancy: bool
    shortage_cost_base: Decimal
    # farqli qatorlar: [{product_id, product_name, quantity, quantity_received}]
    discrepancies: list[dict] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class TransferCancelled(Event):
    name = "transfer.cancelled"
    aggregate_type = "transfer"
    aggregate_id_field = "transfer_id"

    transfer_id: int
    number: str
    from_branch_id: int
    from_branch_name: str
    to_branch_id: int
    to_branch_name: str
    previous_status: str
    reason: str


# --- inventarizatsiya ---


@dataclass(frozen=True, kw_only=True)
class StockCountCreated(Event):
    name = "stock_count.created"
    aggregate_type = "stock_count"
    aggregate_id_field = "count_id"

    count_id: int
    number: str
    items_count: int


@dataclass(frozen=True, kw_only=True)
class StockCountCompleted(Event):
    name = "stock_count.completed"
    aggregate_type = "stock_count"
    aggregate_id_field = "count_id"

    count_id: int
    number: str
    items_counted: int
    surplus_items: int
    shortage_items: int
    surplus_cost_base: Decimal
    shortage_cost_base: Decimal


@dataclass(frozen=True, kw_only=True)
class StockCountCancelled(Event):
    name = "stock_count.cancelled"
    aggregate_type = "stock_count"
    aggregate_id_field = "count_id"

    count_id: int
    number: str


# --- hisobdan chiqarish ---


@dataclass(frozen=True, kw_only=True)
class WriteOffReasonSaved(Event):
    name = "write_off_reason.saved"
    aggregate_type = "write_off_reason"
    aggregate_id_field = "reason_id"

    reason_id: int
    code: str
    created: bool
    changes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, kw_only=True)
class WriteOffCompleted(Event):
    name = "write_off.completed"
    aggregate_type = "write_off"
    aggregate_id_field = "write_off_id"

    write_off_id: int
    number: str
    reason: str
    total_cost_base: Decimal
    items_count: int
    transfer_id: int | None = None


@dataclass(frozen=True, kw_only=True)
class WriteOffCancelled(Event):
    name = "write_off.cancelled"
    aggregate_type = "write_off"
    aggregate_id_field = "write_off_id"

    write_off_id: int
    number: str
    total_cost_base: Decimal
    reason: str
