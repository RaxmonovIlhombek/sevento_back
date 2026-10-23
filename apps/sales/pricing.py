"""Kassa narxi: katalogdagi joriy narx (nuqtaga xos narx ustun). Savdo valyutasida narx bo'lmasa —
sozlama ruxsat bersa — boshqa valyutadagi narx joriy kurs bilan o'tkaziladi (asosiy valyuta
birinchi). Natija savdo valyutasining kasr xonasigacha yaxlitlanadi.

Hisob qoidalari (frontend shu qoidani takrorlaydi, yakuniy summa baribir serverdan):
    qator = yaxlitlash(miqdor × narx) − chegirma;  jami = Σ qator.
"""

from collections.abc import Iterable
from decimal import ROUND_HALF_UP, Decimal

from apps.catalog import selectors as catalog_selectors
from apps.currency import selectors as currency_selectors
from apps.currency.selectors import RateUnavailable
from core import settings_service


def quantum(decimal_places: int) -> Decimal:
    return Decimal(1).scaleb(-decimal_places)


def round_money(value: Decimal, decimal_places: int) -> Decimal:
    return Decimal(value).quantize(quantum(decimal_places), rounding=ROUND_HALF_UP)


def line_gross(quantity: Decimal, unit_price: Decimal, decimal_places: int) -> Decimal:
    return round_money(quantity * unit_price, decimal_places)


def resolve_prices(
    product_ids: Iterable[int],
    *,
    price_type_code: str,
    currency_code: str,
    decimal_places: int,
    branch_id: int,
) -> dict[int, Decimal | None]:
    ids = list(product_ids)
    prices = catalog_selectors.current_prices(ids, branch_id=branch_id)
    allow_convert = settings_service.get("sales.convert_missing_price")
    base = currency_selectors.base_currency_code()
    factors: dict[str, Decimal | None] = {}

    def factor(from_code: str) -> Decimal | None:
        if from_code not in factors:
            try:
                factors[from_code] = currency_selectors.rate_value(
                    from_code
                ) / currency_selectors.rate_value(currency_code)
            except RateUnavailable:
                factors[from_code] = None
        return factors[from_code]

    result: dict[int, Decimal | None] = {}
    for pid in ids:
        rows = [p for p in prices.get(pid, []) if p["price_type"] == price_type_code]
        exact = next((p for p in rows if p["currency"] == currency_code), None)
        if exact is not None:
            result[pid] = round_money(exact["amount"], decimal_places)
            continue
        result[pid] = None
        if not allow_convert:
            continue
        for p in sorted(rows, key=lambda p: (p["currency"] != base, p["currency"])):
            f = factor(p["currency"])
            if f is not None:
                result[pid] = round_money(p["amount"] * f, decimal_places)
                break
    return result
