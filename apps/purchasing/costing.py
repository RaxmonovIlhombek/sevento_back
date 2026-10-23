"""Kirim tannarxi: (qator summasi + xarajat ulushi) / miqdor — asosiy valyutada.

Qoralama uchun oldindan ko'rish ham, qabul qilish ham shu bitta funksiyadan.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from apps.currency import selectors as currency_selectors

from .allocation import AllocationLine, distribute, get_strategy

MONEY = Decimal("0.0001")
UNIT_COST = Decimal("0.000001")


@dataclass
class LineCost:
    line_total: Decimal
    line_total_base: Decimal
    allocated_expense_base: Decimal = Decimal(0)
    landed_unit_cost_base: Decimal = Decimal(0)


@dataclass
class ExpenseCost:
    rate_to_base: Decimal
    amount_base: Decimal


@dataclass
class CostCalculation:
    rate_to_base: Decimal
    subtotal: Decimal
    subtotal_base: Decimal
    expenses_total_base: Decimal
    total_base: Decimal
    lines: list[LineCost] = field(default_factory=list)
    expenses: list[ExpenseCost] = field(default_factory=list)


def _q(value: Decimal, places: Decimal = MONEY) -> Decimal:
    return value.quantize(places, rounding=ROUND_HALF_UP)


def calculate_costs(
    *,
    currency_code: str,
    items: list[tuple[Decimal, Decimal]],  # [(quantity, unit_price)]
    expenses: list[tuple[str, Decimal, str]],  # [(currency_code, amount, allocation_method)]
    on: date | None = None,
) -> CostCalculation:
    """Kurs bo'lmasa currency.RateUnavailable (409)."""
    rate = currency_selectors.rate_to_base(currency_code, on)
    lines = []
    for quantity, unit_price in items:
        line_total = _q(quantity * unit_price)
        lines.append(LineCost(line_total=line_total, line_total_base=_q(line_total * rate)))

    alloc_lines = [
        AllocationLine(quantity=qty, value_base=line.line_total_base)
        for (qty, _), line in zip(items, lines, strict=True)
    ]
    expense_costs = []
    for code, amount, method in expenses:
        exp_rate = currency_selectors.rate_to_base(code, on)
        amount_base = _q(amount * exp_rate)
        expense_costs.append(ExpenseCost(rate_to_base=exp_rate, amount_base=amount_base))
        if lines:
            weights = get_strategy(method).weights(alloc_lines)
            for line, share in zip(lines, distribute(amount_base, weights), strict=True):
                line.allocated_expense_base += share

    for (quantity, _), line in zip(items, lines, strict=True):
        line.landed_unit_cost_base = _q(
            (line.line_total_base + line.allocated_expense_base) / quantity, UNIT_COST
        )

    subtotal = sum((line.line_total for line in lines), Decimal(0))
    subtotal_base = sum((line.line_total_base for line in lines), Decimal(0))
    expenses_total_base = sum((e.amount_base for e in expense_costs), Decimal(0))
    return CostCalculation(
        rate_to_base=rate,
        subtotal=subtotal,
        subtotal_base=subtotal_base,
        expenses_total_base=expenses_total_base,
        total_base=subtotal_base + expenses_total_base,
        lines=lines,
        expenses=expense_costs,
    )
