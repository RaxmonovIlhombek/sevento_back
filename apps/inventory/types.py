from dataclasses import dataclass
from decimal import Decimal

from django.db import models


class MovementType(models.TextChoices):
    PURCHASE_IN = "purchase_in", "Kirim"
    PURCHASE_CANCEL = "purchase_cancel", "Kirim bekor qilindi"
    SALE_OUT = "sale_out", "Savdo"
    SALE_CANCEL = "sale_cancel", "Savdo bekor qilindi"
    SALE_RETURN_IN = "sale_return_in", "Qaytarish"
    TRANSFER_OUT = "transfer_out", "Ko'chirish (jo'natildi)"
    TRANSFER_IN = "transfer_in", "Ko'chirish (qabul qilindi)"
    COUNT_SURPLUS = "count_surplus", "Inventarizatsiya: ortiqcha"
    COUNT_SHORTAGE = "count_shortage", "Inventarizatsiya: kamomad"
    WRITE_OFF = "write_off", "Hisobdan chiqarish"


@dataclass(frozen=True)
class DocRef:
    """Qoldiqni o'zgartirayotgan hujjat (kirim qatori, savdo qatori, ...)."""

    type: str
    id: int
    number: str = ""
    line_id: int | None = None


@dataclass(frozen=True)
class BatchAllocation:
    batch_id: int
    quantity: Decimal
    unit_cost_base: Decimal


@dataclass(frozen=True)
class IssueResult:
    allocations: list[BatchAllocation]
    total_cost_base: Decimal

    @property
    def unit_cost_base(self) -> Decimal:
        qty = sum((a.quantity for a in self.allocations), Decimal(0))
        return (self.total_cost_base / qty) if qty else Decimal(0)
