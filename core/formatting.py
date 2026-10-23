"""Hujjat (chek, PDF hisobot) uchun o'zbekcha son formati: 12 650,45 — lokalga bog'liq emas."""

from decimal import ROUND_HALF_UP, Decimal

NBSP = " "


def format_number(value, places: int = 2, *, trim: bool = False) -> str:
    if value is None:
        return "—"
    d = Decimal(value).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    sign = "-" if d < 0 else ""
    integer, _, fraction = f"{abs(d):f}".partition(".")
    groups = []
    while integer:
        groups.insert(0, integer[-3:])
        integer = integer[:-3]
    text = NBSP.join(groups) or "0"
    if trim:
        fraction = fraction.rstrip("0")
    return f"{sign}{text},{fraction}" if fraction else f"{sign}{text}"
