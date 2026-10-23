from dataclasses import dataclass
from decimal import Decimal

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
