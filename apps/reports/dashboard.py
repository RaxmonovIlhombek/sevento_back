"""Rahbar dashboardi: davr KPI lari (oldingi davr bilan solishtirish), grafiklar uchun qatorlar.

Faqat boshqa app lar selectorlari orqali o'qiydi. Savdo/to'lov/qaytarishda `dashboard.updated`
(WebSocket) keladi — frontend shu ma'lumotni qayta so'raydi.
"""

from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone

from apps.currency import selectors as currency_selectors
from apps.inventory import selectors as inventory_selectors
from apps.payments import selectors as payment_selectors
from apps.sales import selectors as sales_selectors

from .types import percent

Q2 = Decimal("0.01")
ZERO = Decimal(0)
PERIODS = {"today": 1, "7d": 7, "30d": 30, "month": None}


def _q(value) -> Decimal:
    return Decimal(value or 0).quantize(Q2, rounding=ROUND_HALF_UP)


def period_bounds(key: str, today: date | None = None) -> tuple[date, date, date, date]:
    """(boshi, oxiri, oldingi boshi, oldingi oxiri). month — oy boshidan bugungacha."""
    today = today or timezone.localdate()
    if key == "month":
        start = today.replace(day=1)
        prev_end = start - timedelta(days=1)
        length = (today - start).days
        prev_start = prev_end.replace(day=1)
        # oldingi oyning xuddi shuncha kuni (31-kunlik muammosiz)
        prev_end = min(prev_start + timedelta(days=length), prev_end)
        return start, today, prev_start, prev_end
    days = PERIODS[key]
    start = today - timedelta(days=days - 1)
    return start, today, start - timedelta(days=days), start - timedelta(days=1)


def _totals(user, start, end, branch_id) -> dict:
    sales = sales_selectors.sales_by_group(
        user, date_from=start, date_to=end, branch_id=branch_id, group_by="branch"
    )
    returns = sales_selectors.returns_by_group(
        user, date_from=start, date_to=end, branch_id=branch_id, group_by="branch"
    )
    revenue = sum((r["revenue_base"] or ZERO for r in sales), ZERO)
    cost = sum((r["cost_base"] or ZERO for r in sales), ZERO)
    count = sum(r["count"] for r in sales)
    returned = sum((r["total_base"] or ZERO for r in returns), ZERO)
    returned_cost = sum((r["cost_base"] or ZERO for r in returns), ZERO)
    net = revenue - returned
    # foyda = yaxlitlangan tushum − yaxlitlangan tannarx (hisobotlardagi bilan bir xil son)
    return {
        "revenue": _q(net),
        "profit": _q(net) - _q(cost - returned_cost),
        "sales_count": count,
        "average_check": _q(revenue / count) if count else ZERO,
        "returns": _q(returned),
    }


def _kpi(current, previous) -> dict:
    return {
        "value": current,
        "previous": previous,
        "change": percent(current - previous, previous) if previous else None,
    }


def _series(user, start, end, branch_id, hourly: bool) -> list[dict]:
    group_by = "hour" if hourly else "day"
    sales = {
        r["key"]: r
        for r in sales_selectors.sales_by_group(
            user, date_from=start, date_to=end, branch_id=branch_id, group_by=group_by
        )
    }
    returns = {
        r["key"]: r
        for r in sales_selectors.returns_by_group(
            user, date_from=start, date_to=end, branch_id=branch_id, group_by=group_by
        )
    }
    if hourly:
        tz = timezone.get_current_timezone()
        now = timezone.localtime()
        keys = [
            datetime(start.year, start.month, start.day, hour, tzinfo=tz)
            for hour in range(0, now.hour + 1 if start == now.date() else 24)
        ]
        index = {timezone.localtime(k).replace(minute=0, second=0, microsecond=0): k for k in sales}
        index |= {
            timezone.localtime(k).replace(minute=0, second=0, microsecond=0): k for k in returns
        }
    else:
        keys = [start + timedelta(days=i) for i in range((end - start).days + 1)]
        index = {}
    rows = []
    for key in keys:
        source = index.get(key, key)
        s = sales.get(source, {})
        r = returns.get(source, {})
        revenue = (s.get("revenue_base") or ZERO) - (r.get("total_base") or ZERO)
        cost = (s.get("cost_base") or ZERO) - (r.get("cost_base") or ZERO)
        rows.append(
            {
                "label": key.strftime("%H:00") if hourly else key.isoformat(),
                "revenue": _q(revenue),
                "profit": _q(revenue) - _q(cost),
                "count": s.get("count", 0),
            }
        )
    return rows


def build_dashboard(user, *, period: str = "today", branch_id: int | None = None) -> dict:
    start, end, prev_start, prev_end = period_bounds(period)
    current = _totals(user, start, end, branch_id)
    previous = _totals(user, prev_start, prev_end, branch_id)
    show_profit = user.has_capability("reports.financial")
    kpi = {key: _kpi(current[key], previous[key]) for key in current}
    if not show_profit:
        kpi.pop("profit")

    by_branch = [
        {
            "branch": r["label"],
            "revenue": _q(r["revenue_base"]),
            "count": r["count"],
        }
        for r in sales_selectors.sales_by_group(
            user, date_from=start, date_to=end, branch_id=branch_id, group_by="branch"
        )
    ]
    by_branch.sort(key=lambda r: -r["revenue"])
    top = sorted(
        sales_selectors.product_sales(user, date_from=start, date_to=end, branch_id=branch_id),
        key=lambda r: -(r["revenue_base"] or ZERO),
    )[:10]
    debts = payment_selectors.debt_totals(user, branch_id=branch_id)
    return {
        "period": {"key": period, "date_from": start, "date_to": end},
        "base_currency": currency_selectors.base_currency_code(),
        "show_profit": show_profit,
        "kpi": kpi,
        "series": [
            {k: v for k, v in row.items() if show_profit or k != "profit"}
            for row in _series(user, start, end, branch_id, hourly=period == "today")
        ],
        "by_branch": by_branch,
        "top_products": [
            {
                "product_id": r["product__id"],
                "name": r["product__name"],
                "unit": r["product__unit__code"],
                "quantity": r["qty"],
                "revenue": _q(r["revenue_base"]),
            }
            for r in top
        ],
        "payment_methods": [
            {"method": r["method"], "amount": _q(r["amount_base"])}
            for r in sales_selectors.payment_method_totals(
                user, date_from=start, date_to=end, branch_id=branch_id
            )
            if r["amount_base"]
        ],
        "cash": [
            {
                "currency": r["currency__code"],
                "decimal_places": r["currency__decimal_places"],
                "balance": r["balance"],
            }
            for r in payment_selectors.cash_totals(user, branch_id=branch_id)
        ],
        "debts": {
            "open": _q(debts["open_base"]),
            "overdue": _q(debts["overdue_base"]),
            "overdue_count": debts["overdue_count"],
        },
        "inventory": {
            "low_stock": inventory_selectors.low_stock_count(user, branch_id=branch_id),
            "stock_value": _q(inventory_selectors.stock_value_base(user, branch_id=branch_id))
            if user.has_capability("inventory.view_cost")
            else None,
            "incoming_transfers": inventory_selectors.incoming_transfers_count(user),
        },
    }
