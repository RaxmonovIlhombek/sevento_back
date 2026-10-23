from datetime import datetime
from decimal import Decimal
from typing import ClassVar, Protocol

from ..models import Batch
from ..types import BatchAllocation, DocRef


class CostingStrategy(Protocol):
    key: ClassVar[str]

    def on_receive(
        self,
        *,
        branch_id: int,
        product_id: int,
        quantity: Decimal,
        unit_cost_base: Decimal,
        source: DocRef,
        received_at: datetime | None = None,
        parent_batch_id: int | None = None,
    ) -> Batch:
        """Kirimda partiya yaratadi."""
        ...

    def allocate_issue(
        self, *, branch_id: int, product_id: int, quantity: Decimal
    ) -> list[BatchAllocation]:
        """Chiqim uchun qaysi partiyadan qancha va qanday tannarxda olinishi.

        Partiyalarni select_for_update bilan qulflaydi va quantity_remaining ni kamaytiradi.
        Yetmasa InsufficientStock.
        """
        ...
