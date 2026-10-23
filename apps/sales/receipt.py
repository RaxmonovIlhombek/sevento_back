"""Chek PDF (80 mm termoprinter): Django shablon → WeasyPrint. Shrift DejaVu Sans / Noto Sans —
o', g', ʻ, ’ harflari to'g'ri chiqadi (Docker image da fonts-dejavu-core).

Balandlik kontentga moslanadi: avval uzun sahifada o'lchanadi, keyin aniq balandlik bilan qayta
chiziladi — termoprinterda bo'sh qog'oz chiqmasin.
"""

from django.template.loader import render_to_string
from django.utils import timezone

from apps.branches import selectors as branch_selectors
from core import settings_service
from core.formatting import format_number

PAGE_WIDTH = "80mm"
MARGIN_MM = 3
PX_PER_MM = 96 / 25.4


def build_context(sale, payments) -> dict:
    branch = branch_selectors.get_branch(sale.branch_id)
    places = sale.currency.decimal_places
    money = lambda v: format_number(v, places)  # noqa: E731
    items = []
    for item in sale.items.all():
        unit = item.product.unit
        items.append(
            {
                "name": item.product.name,
                "quantity": format_number(item.quantity, unit.decimal_places),
                "unit": unit.code,
                "price": money(item.unit_price),
                "discount": money(item.discount_amount) if item.discount_amount else "",
                "total": money(item.line_total),
            }
        )
    paid = [
        {
            "method": p.method.name,
            "amount": format_number(p.amount, p.currency.decimal_places),
            "currency": p.currency.code,
        }
        for p in payments
        if p.kind == "payment"
    ]
    return {
        "header": settings_service.get("sales.receipt_header") or branch.name,
        "branch_name": branch.name,
        "address": branch.address,
        "phone": branch.phone,
        "number": sale.number,
        "date": timezone.localtime(sale.completed_at).strftime("%d.%m.%Y %H:%M"),
        "seller": sale.seller.full_name,
        "currency": sale.currency.code,
        "items": items,
        "subtotal": money(sale.subtotal),
        "discount_total": money(sale.discount_total) if sale.discount_total else "",
        "total": money(sale.total),
        "payments": paid,
        "change": money(sale.change_amount) if sale.change_amount else "",
        "customer": sale.customer.name if sale.customer_id else "",
        "debt": money(sale.debt_amount) if sale.debt_amount else "",
        "due_date": sale.due_date.strftime("%d.%m.%Y") if sale.due_date else "",
        "cancelled": sale.status == "cancelled",
        "footer": settings_service.get("sales.receipt_footer"),
    }


def render_receipt_pdf(sale, payments) -> bytes:
    from weasyprint import CSS, HTML  # og'ir import faqat kerak bo'lganda

    html = HTML(string=render_to_string("sales/receipt.html", build_context(sale, payments)))
    probe = html.render(
        stylesheets=[CSS(string=f"@page {{ size: {PAGE_WIDTH} 3000mm; margin: {MARGIN_MM}mm }}")]
    )
    content_px = probe.pages[0]._page_box.children[0].margin_height()
    height_px = content_px + 2 * MARGIN_MM * PX_PER_MM + 4
    document = html.render(
        stylesheets=[
            CSS(string=f"@page {{ size: {PAGE_WIDTH} {height_px:.1f}px; margin: {MARGIN_MM}mm }}")
        ]
    )
    return document.write_pdf()
