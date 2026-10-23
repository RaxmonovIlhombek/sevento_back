from dataclasses import dataclass, field
from typing import Any

from core.events import Event


@dataclass(frozen=True, kw_only=True)
class ReportExported(Event):
    """Kim qaysi hisobotni qaysi parametrlar bilan yuklab oldi (audit)."""

    name = "report.exported"
    aggregate_type = "report"

    report_key: str
    format: str
    params: dict[str, Any] = field(default_factory=dict)
    rows: int = 0
    job_id: int | None = None


@dataclass(frozen=True, kw_only=True)
class ReportReady(Event):
    """Fondagi hisobot tayyor — so'ragan foydalanuvchiga (user_{id})."""

    name = "report.ready"
    aggregate_type = "report_job"
    aggregate_id_field = "job_id"
    audit = False

    user_id: int
    job_id: int
    report_key: str
    title: str
    format: str
    download_url: str


@dataclass(frozen=True, kw_only=True)
class ReportFailed(Event):
    name = "report.failed"
    aggregate_type = "report_job"
    aggregate_id_field = "job_id"
    audit = False

    user_id: int
    job_id: int
    report_key: str
    title: str
    error: str
