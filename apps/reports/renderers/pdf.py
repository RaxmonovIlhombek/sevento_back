"""PDF: Django shablon → WeasyPrint. DejaVu Sans — oʻ, gʻ, ʻ to'g'ri chiqadi (fonts-dejavu-core)."""

from django.template.loader import render_to_string
from django.utils import timezone

from core.formatting import format_number

from .base import RenderedReport, cell_text, decimals_for


class PdfRenderer:
    format = "pdf"
    content_type = "application/pdf"
    extension = "pdf"

    def render(self, report: RenderedReport) -> bytes:
        from weasyprint import HTML  # og'ir import faqat kerak bo'lganda

        result = report.result
        columns = result.columns
        rows = [
            [{"text": cell_text(c, row.get(c.key), row), "numeric": c.numeric} for c in columns]
            for row in result.rows
        ]
        totals = None
        if result.totals:
            totals = [
                {
                    "text": format_number(result.totals[c.key], decimals_for(c, None))
                    if c.key in result.totals
                    else "",
                    "numeric": c.numeric,
                }
                for c in columns
            ]
        landscape = report.landscape or len(columns) > 7
        html = render_to_string(
            "reports/report.html",
            {
                "title": report.title,
                "subtitle": report.subtitle,
                "columns": columns,
                "rows": rows,
                "totals": totals,
                "notes": result.notes,
                "generated_by": report.generated_by,
                "generated_at": timezone.localtime(report.generated_at).strftime("%d.%m.%Y %H:%M"),
                "page_size": "A4 landscape" if landscape else "A4",
                "empty": not rows,
            },
        )
        return HTML(string=html).write_pdf()
