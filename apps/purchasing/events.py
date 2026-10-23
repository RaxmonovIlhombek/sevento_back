from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from core.events import Event


@dataclass(frozen=True, kw_only=True)
class SupplierSaved(Event):
    name = "supplier.saved"
    aggregate_type = "supplier"
    aggregate_id_field = "supplier_id"

    supplier_id: int
    supplier_name: str
    created: bool
    changes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, kw_only=True)
class ExpenseTypeSaved(Event):
    name = "expense_type.saved"
    aggregate_type = "expense_type"
    aggregate_id_field = "expense_type_id"

    expense_type_id: int
    code: str
    changes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, kw_only=True)
class PurchaseCreated(Event):
    name = "purchase.created"
    aggregate_type = "purchase"
    aggregate_id_field = "purchase_id"

    purchase_id: int
    number: str
    supplier_id: int


@dataclass(frozen=True, kw_only=True)
class PurchaseReceived(Event):
    name = "purchase.received"
    aggregate_type = "purchase"
    aggregate_id_field = "purchase_id"

    purchase_id: int
    number: str
    supplier_id: int
    currency: str
    rate_to_base: Decimal
    subtotal: Decimal
    expenses_total_base: Decimal
    total_base: Decimal
    # [{product_id, quantity, landed_unit_cost_base}]
    items: list[dict] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class PurchaseCancelled(Event):
    name = "purchase.cancelled"
    aggregate_type = "purchase"
    aggregate_id_field = "purchase_id"

    purchase_id: int
    number: str
    previous_status: str
    reason: str
