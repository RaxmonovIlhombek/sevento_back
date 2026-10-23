from datetime import datetime
from decimal import Decimal

from django.utils import timezone

from ..exceptions import InsufficientStock
from ..models import Batch
from ..types import BatchAllocation, DocRef


class FifoStrategy:
    """Birinchi kirgan — birinchi chiqadi: partiyalar received_at, id tartibida."""

    key = "fifo"

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
        return Batch.objects.create(
            branch_id=branch_id,
            product_id=product_id,
            source_type=source.type,
            source_id=source.id,
            source_line_id=source.line_id,
            source_number=source.number,
            parent_id=parent_batch_id,
            received_at=received_at or timezone.now(),
            quantity_initial=quantity,
            quantity_remaining=quantity,
            unit_cost_base=unit_cost_base,
        )

    def allocate_issue(
        self, *, branch_id: int, product_id: int, quantity: Decimal
    ) -> list[BatchAllocation]:
        batches = (
            Batch.objects.select_for_update()
            .filter(branch_id=branch_id, product_id=product_id, quantity_remaining__gt=0)
            .order_by("received_at", "id")
        )
        need = quantity
        allocations: list[BatchAllocation] = []
        touched: list[Batch] = []
        for batch in batches:
            if need <= 0:
                break
            take = min(batch.quantity_remaining, need)
            batch.quantity_remaining -= take
            need -= take
            touched.append(batch)
            allocations.append(
                BatchAllocation(
                    batch_id=batch.pk, quantity=take, unit_cost_base=batch.unit_cost_base
                )
            )
        if need > 0:
            available = quantity - need
            raise InsufficientStock(
                details=[
                    {
                        "field": "quantity",
                        "code": "insufficient_stock",
                        "message": f"Mavjud: {available.normalize():f}",
                    }
                ]
            )
        Batch.objects.bulk_update(touched, ["quantity_remaining"])
        return allocations
