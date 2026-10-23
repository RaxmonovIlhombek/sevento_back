"""Kirim hisobotlari."""

from decimal import ROUND_HALF_UP, Decimal

from apps.currency import selectors as currency_selectors
from apps.purchasing import selectors as purchasing_selectors

from ..registry import BRANCH, PERIOD, BaseReport, register_report
from ..types import Column, Filter

Q2 = Decimal("0.01")


@register_report
class PurchasesReport(BaseReport):
    key = "purchases"
    title = "Kirimlar"
    description = (
        "Qabul qilingan kirimlar: yetkazib beruvchi, summa, qo'shimcha xarajatlar, tannarx"
    )
    category = "purchasing"
    capability = "purchasing.view"
    landscape = True
    filters = (*PERIOD, BRANCH, Filter("supplier", "supplier", "Yetkazib beruvchi"))

    def columns(self, params):
        base = currency_selectors.base_currency_code()
        return [
            Column("date", "Qabul qilindi", "datetime", width=16),
            Column("number", "Raqam", width=20),
            Column("branch", "Nuqta", width=16),
            Column("supplier", "Yetkazib beruvchi", width=22),
            Column("invoice", "Hisob-faktura", width=14),
            Column("currency", "Valyuta", width=6),
            Column("subtotal", "Summa", "money", decimals_key="_dp"),
            Column("expenses", f"Xarajatlar ({base})", "money", total=True),
            Column("total", f"Jami tannarx ({base})", "money", total=True),
        ]

    def rows(self, params):
        q = lambda v: Decimal(v or 0).quantize(Q2, rounding=ROUND_HALF_UP)  # noqa: E731
        return [
            {
                "date": p.received_at,
                "number": p.number,
                "branch": p.branch.name,
                "supplier": p.supplier.name,
                "invoice": p.invoice_number,
                "currency": p.currency.code,
                "_dp": p.currency.decimal_places,
                "subtotal": p.subtotal,
                "expenses": q(p.expenses_total_base),
                "total": q(p.total_base),
            }
            for p in purchasing_selectors.received_purchases(
                self.user,
                date_from=params["date_from"],
                date_to=params["date_to"],
                branch_id=params.get("branch"),
                supplier_id=params.get("supplier"),
            )
        ]
