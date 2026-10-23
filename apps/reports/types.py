"""Hisobot natijasining yagona formati — JSON, PDF va Excel renderlari shuni chizadi."""

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any


@dataclass(frozen=True)
class Column:
    key: str
    label: str
    # text | number | money | quantity | percent | date | datetime
    type: str = "text"
    decimals: int = 2
    # qatorda o'nlik xonalar soni (masalan hujjat valyutasi: so'm 0, USD 2)
    decimals_key: str | None = None
    total: bool = False  # jami qatorida yig'indi
    capability: str | None = None  # huquq bo'lmasa ustun chiqmaydi (masalan tannarx)
    width: int | None = None  # Excel/PDF uchun taxminiy kenglik (belgi)

    @property
    def numeric(self) -> bool:
        return self.type in {"number", "money", "quantity", "percent"}


@dataclass(frozen=True)
class Filter:
    """Hisobot parametri: frontend shu ro'yxatdan filtr formasini quradi, backend tekshiradi."""

    name: str
    # date | branch | category | supplier | write_off_reason | payment_method | currency
    # | choice | bool
    type: str
    label: str
    required: bool = False
    choices: tuple[tuple[str, str], ...] = ()
    default: Any = None


@dataclass
class ReportResult:
    columns: list[Column]
    rows: list[dict[str, Any]]
    totals: dict[str, Any] | None = None
    notes: list[str] = field(default_factory=list)

    def compute_totals(self) -> None:
        if not any(c.total for c in self.columns):
            return
        totals: dict[str, Any] = {}
        for column in self.columns:
            if column.total:
                totals[column.key] = sum(
                    (Decimal(r[column.key]) for r in self.rows if r.get(column.key) is not None),
                    Decimal(0),
                )
        self.totals = totals


def percent(part, whole) -> Decimal | None:
    """Ulush foizda (1 xona); maxraj 0 bo'lsa — bo'sh."""
    if not whole:
        return None
    return (Decimal(part) * 100 / Decimal(whole)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
