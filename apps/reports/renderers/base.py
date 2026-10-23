from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, ClassVar, Protocol

from django.utils import timezone

from core.exceptions import BusinessRuleError
from core.formatting import format_number

from ..types import Column, ReportResult


@dataclass(frozen=True)
class RenderedReport:
    """Render uchun kontekst: natija + sarlavha ma'lumotlari."""

    title: str
    subtitle: str
    result: ReportResult
    generated_by: str
    generated_at: datetime
    landscape: bool = False


class Renderer(Protocol):
    format: ClassVar[str]
    content_type: ClassVar[str]
    extension: ClassVar[str]

    def render(self, report: RenderedReport) -> bytes: ...


_RENDERERS: dict[str, type] = {}


def register_renderer(cls: type) -> None:
    _RENDERERS[cls.format] = cls


def get_renderer(fmt: str) -> Renderer:
    try:
        return _RENDERERS[fmt]()
    except KeyError:
        raise BusinessRuleError(
            f"Noma'lum format: {fmt}", code="unsupported_format", status_code=400
        ) from None


def renderer_formats() -> list[str]:
    return list(_RENDERERS)


def decimals_for(column: Column, row: dict | None) -> int:
    if column.decimals_key and row and row.get(column.decimals_key) is not None:
        return int(row[column.decimals_key])
    return column.decimals


def cell_text(column: Column, value: Any, row: dict | None = None) -> str:
    """PDF uchun matn: sonlar o'zbekcha (12 650,45), sana dd.mm.yyyy."""
    if value is None or value == "":
        return ""
    if column.numeric:
        places = decimals_for(column, row)
        text = format_number(Decimal(value), places, trim=column.type == "quantity")
        return f"{text}%" if column.type == "percent" else text
    if isinstance(value, datetime):
        return timezone.localtime(value).strftime("%d.%m.%Y %H:%M")
    if isinstance(value, date):
        return value.strftime("%d.%m.%Y")
    return str(value)
