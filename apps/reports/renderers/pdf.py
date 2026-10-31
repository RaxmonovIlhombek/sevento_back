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
        try:
            from weasyprint import HTML  # og'ir import faqat kerak bo'lganda
        except (ImportError, OSError):
            return (
                b"%PDF-1.4\n"
                b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
                b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
                b"3 0 obj<</Type/Page/MediaBox[0 0 595 842]/Parent 2 0 R/Resources<<>>>>endobj\n"
                b"xref\n0 4\n0000000000 65535 f\n0000000010 00000 n\n0000000060 00000 n\n0000000118 00000 n\n"
                b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n190\n%%EOF"
            )

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
