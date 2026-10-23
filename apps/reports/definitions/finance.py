"""Moliya hisobotlari: to'lovlar, kassa harakati, qarzlar, qarzlar muddati bo'yicha (aging)."""

from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone

from apps.currency import selectors as currency_selectors
from apps.payments import selectors as payment_selectors

from ..registry import BRANCH, PERIOD, BaseReport, register_report
from ..types import Column, Filter

Q2 = Decimal("0.01")
ZERO = Decimal(0)


def money(value) -> Decimal:
    return Decimal(value or 0).quantize(Q2, rounding=ROUND_HALF_UP)


@register_report
class PaymentsSummaryReport(BaseReport):
    key = "payments_summary"
    order = 1
    title = "To'lovlar xulosasi"
    description = "To'lov turlari va valyutalar bo'yicha: kirim, chiqim (qaytim, qaytarish), sof"
    category = "finance"
    capability = "reports.financial"
    filters = (*PERIOD, BRANCH)

    def columns(self, params):
        base = currency_selectors.base_currency_code()
        return [
            Column("method", "To'lov turi", width=20),
            Column("currency", "Valyuta", width=6),
            Column("count", "Soni", "number", decimals=0, total=True),
            Column("incoming", "Kirim", "money", decimals_key="_dp"),
            Column("outgoing", "Chiqim", "money", decimals_key="_dp"),
            Column("net", "Sof", "money", decimals_key="_dp"),
            Column("net_base", f"Sof ({base})", "money", total=True),
        ]

    def rows(self, params):
        rows = []
        for r in payment_selectors.payments_summary(
            self.user,
            date_from=params["date_from"],
            date_to=params["date_to"],
            branch_id=params.get("branch"),
        ):
            incoming, outgoing = r["incoming"] or ZERO, r["outgoing"] or ZERO
            rows.append(
                {
                    "method": r["method__name"],
                    "currency": r["currency__code"],
                    "_dp": r["currency__decimal_places"],
                    "count": r["count"],
                    "incoming": incoming,
                    "outgoing": outgoing,
                    "net": incoming - outgoing,
                    "net_base": money((r["incoming_base"] or ZERO) - (r["outgoing_base"] or ZERO)),
                }
            )
        return rows


@register_report
class CashFlowReport(BaseReport):
    key = "cash_flow"
    order = 2
    title = "Kassa hisoboti"
    description = (
        "Kassalar (nuqta × valyuta): davr boshidagi qoldiq, kirim, chiqim, oxiridagi qoldiq"
    )
    category = "finance"
    capability = "reports.financial"
    filters = (*PERIOD, BRANCH, Filter("currency", "currency", "Valyuta"))

    def columns(self, params):
        amount = {"type": "money", "decimals_key": "_dp"}
        return [
            Column("branch", "Nuqta", width=18),
            Column("currency", "Valyuta", width=6),
            Column("opening", "Boshida", **amount),
            Column("incoming", "Kirim", **amount),
            Column("outgoing", "Chiqim", **amount),
            Column("closing", "Oxirida", **amount),
        ]

    def rows(self, params):
        return [
            {**r, "_dp": r.pop("decimal_places")}
            for r in payment_selectors.cash_flow(
                self.user,
                date_from=params["date_from"],
                date_to=params["date_to"],
                branch_id=params.get("branch"),
                currency_code=params.get("currency"),
            )
        ]


@register_report
class DebtsReport(BaseReport):
    key = "debts"
    order = 3
    title = "Qarzlar (nasiya)"
    description = "Ochiq qarzlar: mijoz, hujjat, summa, to'langan, qaytarilgan, qoldiq, muddat"
    category = "finance"
    capability = "reports.financial"
    landscape = True
    filters = (BRANCH, Filter("overdue", "bool", "Faqat muddati o'tganlar", default=False))

    def subtitle(self, params):
        return f"{super().subtitle(params)} · {timezone.localdate():%d.%m.%Y} holatiga"

    def columns(self, params):
        base = currency_selectors.base_currency_code()
        amount = {"type": "money", "decimals_key": "_dp"}
        return [
            Column("customer", "Mijoz", width=22),
            Column("phone", "Telefon", width=14),
            Column("document", "Hujjat", width=20),
            Column("branch", "Nuqta", width=14),
            Column("currency", "Valyuta", width=6),
            Column("amount", "Qarz", **amount),
            Column("paid", "To'langan", **amount),
            Column("returned", "Qaytarilgan", **amount),
            Column("remaining", "Qoldiq", **amount),
            Column("remaining_base", f"Qoldiq ({base})", "money", total=True),
            Column("due_date", "Muddati", "date", width=10),
            Column("overdue", "Kechikish (kun)", "number", decimals=0),
        ]

    def rows(self, params):
        today = timezone.localdate()
        rates: dict[str, Decimal] = {}
        rows = []
        for d in payment_selectors.open_debts(
            self.user, branch_id=params.get("branch"), overdue_only=params.get("overdue") or False
        ):
            code = d.currency.code
            if code not in rates:
                rates[code] = currency_selectors.rate_to_base(code)
            rows.append(
                {
                    "customer": d.customer.name,
                    "phone": d.customer.phone,
                    "document": d.document_number,
                    "branch": d.branch.name,
                    "currency": code,
                    "_dp": d.currency.decimal_places,
                    "amount": d.amount,
                    "paid": d.paid_amount,
                    "returned": d.returned_amount,
                    "remaining": d.remaining_amount,
                    "remaining_base": money(d.remaining_amount * rates[code]),
                    "due_date": d.due_date,
                    "overdue": max((today - d.due_date).days, 0) or None,
                }
            )
        return rows


AGING_BUCKETS = (
    ("current", "Muddati kelmagan", None, 0),
    ("d30", "1–30 kun", 1, 30),
    ("d60", "31–60 kun", 31, 60),
    ("d90", "61–90 kun", 61, 90),
    ("d90plus", "90+ kun", 91, None),
)


@register_report
class DebtsAgingReport(BaseReport):
    key = "debts_aging"
    order = 4
    title = "Qarzlar muddati bo'yicha (aging)"
    description = (
        "Har mijoz qarz qoldig'i kechikish muddatlari bo'yicha, asosiy valyutada (joriy kurs)"
    )
    category = "finance"
    capability = "reports.financial"
    landscape = True
    filters = (BRANCH,)

    def subtitle(self, params):
        return f"{super().subtitle(params)} · {timezone.localdate():%d.%m.%Y} holatiga"

    def columns(self, params):
        base = currency_selectors.base_currency_code()
        return [
            Column("customer", "Mijoz", width=24),
            Column("phone", "Telefon", width=14),
            *[
                Column(key, f"{label} ({base})", "money", total=True)
                for key, label, _, _ in AGING_BUCKETS
            ],
            Column("total", f"Jami ({base})", "money", total=True),
        ]

    def rows(self, params):
        today = timezone.localdate()
        rates: dict[str, Decimal] = {}
        customers: dict[int, dict] = {}
        for d in payment_selectors.open_debts(self.user, branch_id=params.get("branch")):
            code = d.currency.code
            if code not in rates:
                rates[code] = currency_selectors.rate_to_base(code)
            row = customers.setdefault(
                d.customer_id,
                {"customer": d.customer.name, "phone": d.customer.phone}
                | {key: ZERO for key, _, _, _ in AGING_BUCKETS},
            )
            days = (today - d.due_date).days
            bucket = next(
                key
                for key, _, low, high in AGING_BUCKETS
                if (low is None or days >= low) and (high is None or days <= high)
            )
            row[bucket] += d.remaining_amount * rates[code]
        result = []
        for row in customers.values():
            for key, _, _, _ in AGING_BUCKETS:
                row[key] = money(row[key])
            row["total"] = sum((row[key] for key, _, _, _ in AGING_BUCKETS), ZERO)
            result.append(row)
        result.sort(key=lambda r: -r["total"])
        return result
