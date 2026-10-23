"""Savdo hisobotlari: davr bo'yicha xulosa, tovarlar bo'yicha savdo va foyda, qaytarishlar."""

from decimal import ROUND_HALF_UP, Decimal

from apps.catalog import selectors as catalog_selectors
from apps.currency import selectors as currency_selectors
from apps.sales import selectors as sales_selectors

from ..registry import BRANCH, PERIOD, BaseReport, register_report
from ..types import Column, Filter, percent

Q2 = Decimal("0.01")
ZERO = Decimal(0)


def money(value) -> Decimal:
    return Decimal(value or 0).quantize(Q2, rounding=ROUND_HALF_UP)


def base_label() -> str:
    return currency_selectors.base_currency_code()


@register_report
class SalesSummaryReport(BaseReport):
    key = "sales_summary"
    order = 1
    title = "Savdo hisoboti"
    description = "Kunlar, nuqtalar yoki sotuvchilar bo'yicha: savdo, qaytarish, sof tushum, foyda"
    category = "sales"
    capability = "reports.financial"
    filters = (
        *PERIOD,
        BRANCH,
        Filter(
            "group_by",
            "choice",
            "Guruhlash",
            choices=(("day", "Kunlar"), ("branch", "Nuqtalar"), ("seller", "Sotuvchilar")),
            default="day",
        ),
    )

    def columns(self, params):
        base = base_label()
        first = {"day": "Sana", "branch": "Nuqta", "seller": "Sotuvchi"}[params["group_by"]]
        return [
            Column("group", first, "date" if params["group_by"] == "day" else "text", width=18),
            Column("count", "Savdolar", "number", decimals=0, total=True),
            Column("revenue", f"Savdo ({base})", "money", total=True),
            Column("discount", f"Chegirma ({base})", "money", total=True),
            Column("returns", f"Qaytarish ({base})", "money", total=True),
            Column("net", f"Sof tushum ({base})", "money", total=True),
            Column("cost", f"Tannarx ({base})", "money", total=True),
            Column("profit", f"Yalpi foyda ({base})", "money", total=True),
            Column("margin", "Rentabellik", "percent", decimals=1),
        ]

    def rows(self, params):
        args = {
            "date_from": params["date_from"],
            "date_to": params["date_to"],
            "branch_id": params.get("branch"),
            "group_by": params["group_by"],
        }
        groups: dict = {}
        for r in sales_selectors.sales_by_group(self.user, **args):
            groups[r["key"]] = {
                "group": r.get("label", r["key"]),
                "count": r["count"],
                "revenue": money(r["revenue_base"]),
                "discount": money(r["discount_base"]),
                "cost": money(r["cost_base"]),
                "returns": ZERO,
                "returns_cost": ZERO,
            }
        for r in sales_selectors.returns_by_group(self.user, **args):
            row = groups.setdefault(
                r["key"],
                {
                    "group": r.get("label", r["key"]),
                    "count": 0,
                    "revenue": ZERO,
                    "discount": ZERO,
                    "cost": ZERO,
                },
            )
            row["returns"] = money(r["total_base"])
            row["returns_cost"] = money(r["cost_base"])
        result = []
        for key in sorted(groups, key=lambda k: (str(groups[k]["group"]) if k else "")):
            row = groups[key]
            net = row["revenue"] - row["returns"]
            cost = row["cost"] - row["returns_cost"]
            result.append(
                {
                    **row,
                    "net": net,
                    "cost": cost,
                    "profit": net - cost,
                    "margin": percent(net - cost, net),
                }
            )
        if params["group_by"] == "day":
            result.sort(key=lambda r: r["group"])
        return result


@register_report
class SalesByProductReport(BaseReport):
    key = "sales_by_product"
    order = 2
    title = "Tovarlar bo'yicha savdo va foyda"
    description = (
        "Sotilgan va qaytarilgan miqdor, sof tushum, tannarx, foyda (tovar yoki kategoriya)"
    )
    category = "sales"
    capability = "reports.financial"
    landscape = True
    filters = (
        *PERIOD,
        BRANCH,
        Filter("category", "category", "Kategoriya"),
        Filter(
            "group_by",
            "choice",
            "Guruhlash",
            choices=(("product", "Tovarlar"), ("category", "Kategoriyalar")),
            default="product",
        ),
    )

    def columns(self, params):
        base = base_label()
        by_product = params["group_by"] == "product"
        head = (
            [
                Column("name", "Tovar", width=30),
                Column("sku", "Artikul", width=12),
                Column("unit", "Birlik", width=6),
            ]
            if by_product
            else [Column("name", "Kategoriya", width=30)]
        )
        qty = {"decimals_key": "_qdp"} if by_product else {}
        return [
            *head,
            Column("sold", "Sotildi", "quantity", decimals=3, total=not by_product, **qty),
            Column("returned", "Qaytdi", "quantity", decimals=3, total=not by_product, **qty),
            Column("net_qty", "Sof miqdor", "quantity", decimals=3, total=not by_product, **qty),
            Column("revenue", f"Sof tushum ({base})", "money", total=True),
            Column("cost", f"Tannarx ({base})", "money", total=True),
            Column("profit", f"Foyda ({base})", "money", total=True),
            Column("margin", "Rentabellik", "percent", decimals=1),
        ]

    def rows(self, params):
        group_by = params["group_by"]
        category_ids = (
            catalog_selectors.descendant_ids(params["category"]) if params.get("category") else None
        )
        args = {
            "date_from": params["date_from"],
            "date_to": params["date_to"],
            "branch_id": params.get("branch"),
            "category_ids": category_ids,
            "group_by": group_by,
        }
        key_field = "product__id" if group_by == "product" else "product__category_id"
        rows: dict = {}

        def blank(r):
            if group_by == "product":
                return {
                    "name": r["product__name"],
                    "sku": r["product__sku"],
                    "unit": r["product__unit__code"],
                    "_qdp": r["product__unit__decimal_places"],
                }
            return {"name": r["product__category__name"] or "Kategoriyasiz"}

        for r in sales_selectors.product_sales(self.user, **args):
            row = rows.setdefault(r[key_field], blank(r))
            row.update(sold=r["qty"], revenue=money(r["revenue_base"]), cost=money(r["cost_base"]))
        for r in sales_selectors.product_returns(self.user, **args):
            row = rows.setdefault(r[key_field], blank(r))
            row.update(
                returned=r["qty"], ret_total=money(r["total_base"]), ret_cost=money(r["cost_base"])
            )
        result = []
        for row in rows.values():
            sold, returned = row.get("sold", ZERO), row.get("returned", ZERO)
            revenue = row.get("revenue", ZERO) - row.pop("ret_total", ZERO)
            cost = row.get("cost", ZERO) - row.pop("ret_cost", ZERO)
            result.append(
                {
                    **row,
                    "sold": sold,
                    "returned": returned,
                    "net_qty": sold - returned,
                    "revenue": revenue,
                    "cost": cost,
                    "profit": revenue - cost,
                    "margin": percent(revenue - cost, revenue),
                }
            )
        result.sort(key=lambda r: (-r["revenue"], r["name"]))
        return result


@register_report
class ReturnsReport(BaseReport):
    key = "returns"
    order = 3
    title = "Qaytarishlar"
    description = "Qaytarilgan tovarlar: summa, qarzdan ayirilgan va mijozga qaytarilgan pul"
    category = "sales"
    capability = "reports.financial"
    landscape = True
    filters = (*PERIOD, BRANCH)

    def columns(self, params):
        base = base_label()
        return [
            Column("date", "Vaqt", "datetime", width=16),
            Column("number", "Qaytarish", width=20),
            Column("sale", "Savdo", width=20),
            Column("branch", "Nuqta", width=16),
            Column("customer", "Mijoz", width=20),
            Column("currency", "Valyuta", width=6),
            Column("total", "Summa", "money", decimals_key="_dp"),
            Column("debt", "Qarzdan", "money", decimals_key="_dp"),
            Column("refund", "Pul qaytdi", "money", decimals_key="_dp"),
            Column("total_base", f"Summa ({base})", "money", total=True),
            Column("reason", "Sabab", width=24),
        ]

    def rows(self, params):
        return [
            {
                "date": r.created_at,
                "number": r.number,
                "sale": r.sale.number,
                "branch": r.branch.name,
                "customer": r.customer.name if r.customer_id else "",
                "currency": r.currency.code,
                "_dp": r.currency.decimal_places,
                "total": r.total,
                "debt": r.debt_reduction,
                "refund": r.refund_amount,
                "total_base": money(r.total_base),
                "reason": r.reason,
            }
            for r in sales_selectors.returns_report(
                self.user,
                date_from=params["date_from"],
                date_to=params["date_to"],
                branch_id=params.get("branch"),
            )
        ]
