"""Hisobotlar reyestri (strategiya naqshi): yangi hisobot — `definitions/<nom>.py` da
`@register_report` bilan klass. Mavjud kod (view, render, frontend) o'zgarmaydi.
"""

from datetime import date
from typing import Any, ClassVar

from django.utils import timezone
from django.utils.dateparse import parse_date

from apps.branches import selectors as branch_selectors
from core import settings_service
from core.access import ensure_branch_access
from core.exceptions import BusinessRuleError, NotFoundError

from .types import Column, Filter, ReportResult

_REPORTS: dict[str, type["BaseReport"]] = {}

# Ko'p ishlatiladigan filtrlar
DATE_FROM = Filter("date_from", "date", "Sanadan")
DATE_TO = Filter("date_to", "date", "Sanagacha")
PERIOD = (DATE_FROM, DATE_TO)
BRANCH = Filter("branch", "branch", "Nuqta")

CATEGORIES = {
    "sales": "Savdo",
    "inventory": "Ombor",
    "purchasing": "Kirim",
    "finance": "Moliya",
}


class BaseReport:
    key: ClassVar[str]
    title: ClassVar[str]
    description: ClassVar[str] = ""
    category: ClassVar[str] = "sales"
    capability: ClassVar[str] = "reports.view"
    filters: ClassVar[tuple[Filter, ...]] = ()
    # doim fonda tayyorlanadi (masalan butun harakatlar jurnali)
    heavy: ClassVar[bool] = False
    landscape: ClassVar[bool] = False
    order: ClassVar[int] = 100  # bo'lim ichidagi tartib

    def __init__(self, user):
        self.user = user

    # --- ta'rif ---

    def columns(self, params: dict) -> list[Column]:
        raise NotImplementedError

    def rows(self, params: dict) -> list[dict[str, Any]]:
        raise NotImplementedError

    # --- umumiy ---

    @classmethod
    def allowed(cls, user) -> bool:
        return user.has_capability(cls.capability)

    def run(self, params: dict) -> ReportResult:
        columns = [
            c
            for c in self.columns(params)
            if not c.capability or self.user.has_capability(c.capability)
        ]
        keys = {c.key for c in columns}
        rows = [
            {k: v for k, v in row.items() if k in keys or k.startswith("_")}
            for row in self.rows(params)
        ]
        result = ReportResult(columns=columns, rows=rows)
        result.compute_totals()
        return result

    def is_heavy(self, params: dict) -> bool:
        """Fonda (Celery) tayyorlanadimi: belgilangan og'ir hisobot yoki uzun davr."""
        if self.heavy:
            return True
        start, end = params.get("date_from"), params.get("date_to")
        if isinstance(start, date) and isinstance(end, date):
            return (end - start).days + 1 > int(settings_service.get("reports.sync_max_days"))
        return False

    def subtitle(self, params: dict) -> str:
        parts = []
        start, end = params.get("date_from"), params.get("date_to")
        if isinstance(start, date) and isinstance(end, date):
            parts.append(f"{start:%d.%m.%Y} — {end:%d.%m.%Y}")
        elif isinstance(end, date):
            parts.append(f"{end:%d.%m.%Y} holatiga")
        branch_id = params.get("branch")
        if branch_id:
            branch = branch_selectors.get_branch(branch_id)
            parts.append(branch.name if branch else f"#{branch_id}")
        else:
            parts.append("Barcha nuqtalar")
        return " · ".join(parts)

    # --- parametrlar ---

    @classmethod
    def parse_params(cls, data, user) -> dict:
        """So'rov parametrlari → toza qiymatlar. Xato bo'lsa 400 (maydon bo'yicha)."""
        params: dict[str, Any] = {}
        errors: list[dict] = []
        today = timezone.localdate()
        for f in cls.filters:
            raw = data.get(f.name)
            raw = raw.strip() if isinstance(raw, str) else raw
            value: Any = None
            if raw in (None, ""):
                if f.type == "date":
                    value = today.replace(day=1) if f.name == "date_from" else today
                elif f.default is not None:
                    value = f.default
                elif f.required:
                    errors.append({"field": f.name, "code": "required", "message": "Majburiy"})
                    continue
                params[f.name] = value
                continue
            if f.type == "date":
                try:
                    value = parse_date(str(raw)) if isinstance(raw, str) else raw
                except ValueError:  # 2026-13-01 kabi — format to'g'ri, sana yo'q
                    value = None
                if not isinstance(value, date):
                    errors.append(
                        {"field": f.name, "code": "invalid", "message": "Sana YYYY-MM-DD"}
                    )
                    continue
            elif f.type == "bool":
                value = str(raw).lower() in {"1", "true", "yes", "on"}
            elif f.type == "choice":
                value = str(raw)
                if value not in {c for c, _ in f.choices}:
                    errors.append({"field": f.name, "code": "invalid_choice", "message": value})
                    continue
            elif f.type == "currency":
                value = str(raw).upper()
            else:  # id li ma'lumotnomalar: branch, category, supplier, ...
                try:
                    value = int(raw)
                except (TypeError, ValueError):
                    errors.append({"field": f.name, "code": "invalid", "message": "Butun son"})
                    continue
            params[f.name] = value
        start, end = params.get("date_from"), params.get("date_to")
        if isinstance(start, date) and isinstance(end, date) and start > end:
            errors.append(
                {
                    "field": "date_from",
                    "code": "invalid_range",
                    "message": "Boshlanish oxiridan keyin",
                }
            )
        if errors:
            raise BusinessRuleError(
                "Hisobot parametrlari noto'g'ri",
                code="validation_error",
                status_code=400,
                details=errors,
            )
        if params.get("branch"):
            ensure_branch_access(user, params["branch"])
        return params


def register_report(cls: type[BaseReport]) -> type[BaseReport]:
    if cls.key in _REPORTS and _REPORTS[cls.key] is not cls:
        raise ValueError(f"Hisobot kaliti takrorlangan: {cls.key}")
    _REPORTS[cls.key] = cls
    return cls


def get_report(key: str) -> type[BaseReport]:
    try:
        return _REPORTS[key]
    except KeyError:
        raise NotFoundError("Bunday hisobot yo'q", code="report_not_found") from None


def all_reports() -> list[type[BaseReport]]:
    order = list(CATEGORIES)
    return sorted(
        _REPORTS.values(),
        key=lambda r: (order.index(r.category) if r.category in order else 99, r.order, r.title),
    )


def reports_for(user) -> list[type[BaseReport]]:
    return [r for r in all_reports() if r.allowed(user)]
