"""Ombor hisobotlari: qoldiq, aylanma, harakatlar jurnali, ko'chirishlar, hisobdan chiqarish."""

from decimal import ROUND_HALF_UP, Decimal

from apps.catalog import selectors as catalog_selectors
from apps.currency import selectors as currency_selectors
from apps.inventory import selectors as inventory_selectors
from apps.inventory.types import MovementType

from ..registry import BRANCH, PERIOD, BaseReport, register_report
from ..types import Column, Filter

COST = "inventory.view_cost"
Q2 = Decimal("0.01")
CATEGORY = Filter("category", "category", "Kategoriya")


def money(value) -> Decimal:
    return Decimal(value or 0).quantize(Q2, rounding=ROUND_HALF_UP)


def category_ids(params):
    return catalog_selectors.descendant_ids(params["category"]) if params.get("category") else None


def product_columns() -> list[Column]:
    return [
        Column("product", "Tovar", width=30),
        Column("sku", "Artikul", width=12),
        Column("unit", "Birlik", width=6),
    ]


@register_report
class StockBalanceReport(BaseReport):
    key = "stock_balance"
    order = 1
    title = "Qoldiq hisoboti"
    description = "Nuqtalar bo'yicha joriy qoldiq, minimal qoldiq va tannarx bo'yicha qiymati"
    category = "inventory"
    filters = (
        BRANCH,
        CATEGORY,
        Filter("below_min", "bool", "Faqat kam qolganlar", default=False),
        Filter("include_zero", "bool", "Tugaganlar ham", default=False),
    )

    def subtitle(self, params):
        return f"{super().subtitle(params)} · joriy holat"

    def columns(self, params):
        base = currency_selectors.base_currency_code()
        return [
            *product_columns(),
            Column("category", "Kategoriya", width=16),
            Column("branch", "Nuqta", width=16),
            Column("quantity", "Qoldiq", "quantity", decimals=3, decimals_key="_qdp"),
            Column("min", "Minimal", "quantity", decimals=3, decimals_key="_qdp"),
            Column("value", f"Qiymat ({base})", "money", total=True, capability=COST),
        ]

    def rows(self, params):
        return [
            {
                "product": level.product.name,
                "sku": level.product.sku,
                "unit": level.product.unit.code,
                "_qdp": level.product.unit.decimal_places,
                "category": level.product.category.name if level.product.category_id else "",
                "branch": level.branch.name,
                "quantity": level.quantity,
                "min": level.effective_min,
                "value": money(level.value_base),
            }
            for level in inventory_selectors.stock_report(
                self.user,
                branch_id=params.get("branch"),
                category_ids=category_ids(params),
                below_min=params.get("below_min") or False,
                include_zero=params.get("include_zero") or False,
            )
        ]


@register_report
class StockTurnoverReport(BaseReport):
    key = "stock_turnover"
    order = 2
    title = "Tovar aylanmasi"
    description = (
        "Davr boshidagi qoldiq, kirim, savdo (qaytarish bilan), ko'chirish, "
        "inventarizatsiya va hisobdan chiqarish, davr oxiridagi qoldiq"
    )
    category = "inventory"
    landscape = True
    filters = (*PERIOD, BRANCH, CATEGORY)

    def columns(self, params):
        qty = {"type": "quantity", "decimals": 3, "decimals_key": "_qdp"}
        return [
            *product_columns(),
            Column("opening", "Boshida", **qty),
            Column("purchases", "Kirim", **qty),
            Column("sales", "Savdo", **qty),
            Column("transfers", "Ko'chirish", **qty),
            Column("adjustments", "Tuzatish", **qty),
            Column("closing", "Oxirida", **qty),
        ]

    def rows(self, params):
        return [
            {
                "product": r["product__name"],
                "sku": r["product__sku"],
                "unit": r["product__unit__code"],
                "_qdp": r["product__unit__decimal_places"],
                "opening": r["opening"],
                "purchases": r["purchases"],
                "sales": r["sales"],
                "transfers": r["transfers"],
                "adjustments": r["adjustments"],
                "closing": r["closing"],
            }
            for r in inventory_selectors.turnover(
                self.user,
                date_from=params["date_from"],
                date_to=params["date_to"],
                branch_id=params.get("branch"),
                category_ids=category_ids(params),
            )
        ]


@register_report
class StockMovementsReport(BaseReport):
    key = "stock_movements"
    order = 3
    title = "Ombor harakatlari jurnali"
    description = (
        "Har bir kirim va chiqim: hujjat, miqdor, qoldiq (katta hajm — fonda tayyorlanadi)"
    )
    category = "inventory"
    heavy = True
    landscape = True
    filters = (
        *PERIOD,
        BRANCH,
        Filter("type", "choice", "Harakat turi", choices=tuple(MovementType.choices)),
    )

    def columns(self, params):
        base = currency_selectors.base_currency_code()
        return [
            Column("date", "Vaqt", "datetime", width=16),
            Column("branch", "Nuqta", width=14),
            Column("product", "Tovar", width=28),
            Column("type", "Harakat", width=20),
            Column("quantity", "Miqdor", "quantity", decimals=3, decimals_key="_qdp"),
            Column("balance", "Qoldiq", "quantity", decimals=3, decimals_key="_qdp"),
            Column("cost", f"Tannarx ({base})", "money", total=True, capability=COST),
            Column("document", "Hujjat", width=20),
            Column("user", "Kim", width=14),
        ]

    def rows(self, params):
        return [
            {
                "date": m.created_at,
                "branch": m.branch.name,
                "product": m.product.name,
                "_qdp": m.product.unit.decimal_places,
                "type": m.get_type_display(),
                "quantity": m.quantity,
                "balance": m.balance_after,
                "cost": money(m.total_cost_base),
                "document": m.document_number,
                "user": m.created_by.full_name if m.created_by_id else "",
            }
            for m in inventory_selectors.movements_report(
                self.user,
                date_from=params["date_from"],
                date_to=params["date_to"],
                branch_id=params.get("branch"),
                movement_type=params.get("type"),
            )
        ]


@register_report
class TransfersReport(BaseReport):
    key = "transfers"
    order = 4
    title = "Ko'chirishlar"
    description = "Nuqtalar orasidagi ko'chirishlar: holat, tannarx, kamomad"
    category = "inventory"
    landscape = True
    filters = (
        *PERIOD,
        BRANCH,
        Filter(
            "status",
            "choice",
            "Holat",
            choices=(
                ("draft", "Qoralama"),
                ("sent", "Yo'lda"),
                ("received", "Qabul qilindi"),
                ("cancelled", "Bekor qilindi"),
            ),
        ),
    )

    def columns(self, params):
        base = currency_selectors.base_currency_code()
        return [
            Column("number", "Raqam", width=20),
            Column("date", "Yaratildi", "datetime", width=16),
            Column("from", "Qayerdan", width=16),
            Column("to", "Qayerga", width=16),
            Column("items", "Qatorlar", "number", decimals=0),
            Column("status", "Holat", width=12),
            Column("received", "Qabul qilindi", "datetime", width=16),
            Column("cost", f"Tannarx ({base})", "money", total=True, capability=COST),
            Column("shortage", f"Kamomad ({base})", "money", total=True, capability=COST),
        ]

    def rows(self, params):
        return [
            {
                "number": t.number,
                "date": t.created_at,
                "from": t.from_branch.name,
                "to": t.to_branch.name,
                "items": t.items_count,
                "status": t.get_status_display(),
                "received": t.received_at,
                "cost": money(t.total_cost_base),
                "shortage": money(t.shortage_cost_base),
            }
            for t in inventory_selectors.transfers_report(
                self.user,
                date_from=params["date_from"],
                date_to=params["date_to"],
                branch_id=params.get("branch"),
                status=params.get("status"),
            )
        ]


@register_report
class WriteOffsReport(BaseReport):
    key = "write_offs"
    order = 5
    title = "Hisobdan chiqarishlar"
    description = "Sabablar bo'yicha hisobdan chiqarilgan tovarlar va ularning tannarxi"
    category = "inventory"
    landscape = True
    filters = (*PERIOD, BRANCH, Filter("reason", "write_off_reason", "Sabab"))

    def columns(self, params):
        base = currency_selectors.base_currency_code()
        return [
            Column("date", "Sana", "datetime", width=16),
            Column("number", "Hujjat", width=20),
            Column("branch", "Nuqta", width=16),
            Column("reason", "Sabab", width=18),
            Column("product", "Tovar", width=28),
            Column("quantity", "Miqdor", "quantity", decimals=3, decimals_key="_qdp"),
            Column("unit", "Birlik", width=6),
            Column("cost", f"Tannarx ({base})", "money", total=True, capability=COST),
        ]

    def rows(self, params):
        return [
            {
                "date": line.write_off.completed_at,
                "number": line.write_off.number,
                "branch": line.write_off.branch.name,
                "reason": line.write_off.reason.name,
                "product": line.product.name,
                "quantity": line.quantity,
                "_qdp": line.product.unit.decimal_places,
                "unit": line.product.unit.code,
                "cost": money(line.total_cost_base),
            }
            for line in inventory_selectors.write_off_lines(
                self.user,
                date_from=params["date_from"],
                date_to=params["date_to"],
                branch_id=params.get("branch"),
                reason_id=params.get("reason"),
            )
        ]
