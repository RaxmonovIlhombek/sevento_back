from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from core.events import Event


@dataclass(frozen=True, kw_only=True)
class CategoryCreated(Event):
    name = "category.created"
    aggregate_type = "category"
    aggregate_id_field = "category_id"

    category_id: int
    category_name: str
    parent_id: int | None


@dataclass(frozen=True, kw_only=True)
class CategoryUpdated(Event):
    name = "category.updated"
    aggregate_type = "category"
    aggregate_id_field = "category_id"

    category_id: int
    changes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, kw_only=True)
class UnitSaved(Event):
    name = "unit.saved"
    aggregate_type = "unit"
    aggregate_id_field = "unit_id"

    unit_id: int
    code: str
    changes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, kw_only=True)
class PriceTypeSaved(Event):
    name = "price_type.saved"
    aggregate_type = "price_type"
    aggregate_id_field = "price_type_id"

    price_type_id: int
    code: str
    changes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, kw_only=True)
class ProductCreated(Event):
    name = "product.created"
    aggregate_type = "product"
    aggregate_id_field = "product_id"

    product_id: int
    sku: str
    product_name: str


@dataclass(frozen=True, kw_only=True)
class ProductUpdated(Event):
    name = "product.updated"
    aggregate_type = "product"
    aggregate_id_field = "product_id"

    product_id: int
    sku: str
    changes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, kw_only=True)
class ProductPriceChanged(Event):
    name = "product.price_changed"
    aggregate_type = "product"
    aggregate_id_field = "product_id"

    product_id: int
    price_type: str
    currency: str
    old_amount: Decimal | None
    new_amount: Decimal
