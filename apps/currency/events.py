from dataclasses import dataclass, field
from typing import Any

from core.events import Event


@dataclass(frozen=True, kw_only=True)
class CurrencyCreated(Event):
    name = "currency.created"
    aggregate_type = "currency"
    aggregate_id_field = "currency_id"

    currency_id: int
    code: str


@dataclass(frozen=True, kw_only=True)
class CurrencyUpdated(Event):
    name = "currency.updated"
    aggregate_type = "currency"
    aggregate_id_field = "currency_id"

    currency_id: int
    code: str
    changes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, kw_only=True)
class RateUpdated(Event):
    """Kurs(lar) yangilandi — qo'lda yoki provayderdan. Hammaga WebSocket orqali ham boradi."""

    name = "currency.rate_updated"
    aggregate_type = "exchange_rate"

    source: str
    rates: list[dict] = field(default_factory=list)  # [{currency, rate, date}]
