from dataclasses import dataclass

from core.events import Event


@dataclass(frozen=True, kw_only=True)
class FulfillmentStatusChanged(Event):
    name = "fulfillment.status_changed"
    aggregate_type = "fulfillment"
    aggregate_id_field = "fulfillment_id"

    fulfillment_id: int
    sale_id: int
    number: str
    status: str
    previous_status: str | None = None
    courier_id: int | None = None
    note: str = ""
