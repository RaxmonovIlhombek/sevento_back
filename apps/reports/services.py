"""Hisobot: ko'rish (JSON), fayl (sinxron yoki fonda — Celery), fayllarni tozalash.

Qisqa davr — fayl darhol qaytariladi; og'ir hisobot yoki uzun davr — `ReportJob` yaratiladi,
Celery tayyorlaydi va `report.ready` (WebSocket, user_{id}) bilan xabar beradi.
"""

import logging
from dataclasses import dataclass
from datetime import date, timedelta

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from apps.accounts import selectors as account_selectors
from core import settings_service
from core.exceptions import BusinessRuleError

from . import events
from .models import ReportJob
from .registry import BaseReport, get_report
from .renderers import RenderedReport, get_renderer
from .types import ReportResult

log = logging.getLogger("reports")


@dataclass(frozen=True)
class FileExport:
    content: bytes
    filename: str
    content_type: str
    rows: int


def _instance(user, key: str) -> BaseReport:
    report_cls = get_report(key)
    if not report_cls.allowed(user):
        raise BusinessRuleError(
            "Bu hisobotga ruxsat yo'q", code="permission_denied", status_code=403
        )
    return report_cls(user)


def _jsonable(params: dict) -> dict:
    return {k: (v.isoformat() if isinstance(v, date) else v) for k, v in params.items()}


def preview(*, user, key: str, data) -> dict:
    """Ekran uchun: ustunlar, qatorlar (cheklangan), jami, umumiy qatorlar soni."""
    report = _instance(user, key)
    params = report.parse_params(data, user)
    result = report.run(params)
    limit = int(settings_service.get("reports.preview_row_limit"))
    return {
        "key": report.key,
        "title": report.title,
        "subtitle": report.subtitle(params),
        "params": _jsonable(params),
        "columns": result.columns,
        "rows": result.rows[:limit],
        "totals": result.totals,
        "notes": result.notes,
        "row_count": len(result.rows),
        "truncated": len(result.rows) > limit,
        "heavy": report.is_heavy(params),
    }


def _render(report: BaseReport, params: dict, result: ReportResult, fmt: str, user) -> bytes:
    return get_renderer(fmt).render(
        RenderedReport(
            title=report.title,
            subtitle=report.subtitle(params),
            result=result,
            generated_by=user.full_name or user.username,
            generated_at=timezone.now(),
            landscape=report.landscape,
        )
    )


def _filename(report: BaseReport, fmt: str) -> str:
    return f"{report.key}-{timezone.localdate():%Y%m%d}.{get_renderer(fmt).extension}"


def export(*, user, key: str, fmt: str, data) -> FileExport | ReportJob:
    """Fayl: yengil — darhol (bytes), og'ir — fon vazifasi (ReportJob, 202)."""
    report = _instance(user, key)
    renderer = get_renderer(fmt)  # noma'lum format → 400 darhol
    params = report.parse_params(data, user)
    if report.is_heavy(params):
        with transaction.atomic():
            job = ReportJob.objects.create(
                report_key=report.key,
                title=report.title,
                params=_jsonable(params),
                format=fmt,
                requested_by=user,
            )
            events.ReportExported.publish_from(
                actor=user, report_key=report.key, format=fmt, params=job.params, job_id=job.pk
            )
            from .tasks import generate_report

            transaction.on_commit(lambda: generate_report.delay(job.pk))
        return job
    result = report.run(params)
    content = _render(report, params, result, fmt, user)
    with transaction.atomic():
        events.ReportExported.publish_from(
            actor=user,
            report_key=report.key,
            format=fmt,
            params=_jsonable(params),
            rows=len(result.rows),
        )
    return FileExport(
        content=content,
        filename=_filename(report, fmt),
        content_type=renderer.content_type,
        rows=len(result.rows),
    )


def download_url(job: ReportJob) -> str:
    return f"/api/v1/reports/jobs/{job.pk}/download/"


def run_job(job_id: int) -> ReportJob:
    """Celery: so'ragan foydalanuvchi huquqlari va nuqtalari bilan hisoblanadi."""
    job = ReportJob.objects.select_related("requested_by").get(pk=job_id)
    if job.status not in (ReportJob.Status.PENDING, ReportJob.Status.FAILED):
        return job
    job.status = ReportJob.Status.RUNNING
    job.started_at = timezone.now()
    job.save(update_fields=["status", "started_at"])
    user = account_selectors.get_user(job.requested_by_id)
    try:
        report = _instance(user, job.report_key)
        params = report.parse_params(job.params, user)
        result = report.run(params)
        content = _render(report, params, result, job.format, user)
        job.file.save(f"{job.pk}-{_filename(report, job.format)}", ContentFile(content), save=False)
        job.rows_count = len(result.rows)
        job.status = ReportJob.Status.READY
        job.finished_at = timezone.now()
        with transaction.atomic():
            job.save(update_fields=["file", "rows_count", "status", "finished_at"])
            events.ReportReady.publish_from(
                actor=user,
                user_id=user.pk,
                job_id=job.pk,
                report_key=job.report_key,
                title=job.title,
                format=job.format,
                download_url=download_url(job),
            )
    except Exception as exc:  # noqa: BLE001 — foydalanuvchiga xabar, log da to'liq
        log.exception("Hisobot tayyorlanmadi: job %s", job.pk)
        job.status = ReportJob.Status.FAILED
        job.error = str(getattr(exc, "message", exc))[:500]
        job.finished_at = timezone.now()
        with transaction.atomic():
            job.save(update_fields=["status", "error", "finished_at"])
            events.ReportFailed.publish_from(
                actor=user,
                user_id=job.requested_by_id,
                job_id=job.pk,
                report_key=job.report_key,
                title=job.title,
                error=job.error,
            )
    return job


def cleanup_old_jobs(now=None) -> int:
    """Saqlash muddati o'tgan fayllar va yozuvlar o'chiriladi."""
    now = now or timezone.now()
    border = now - timedelta(days=int(settings_service.get("reports.keep_days")))
    removed = 0
    for job in ReportJob.objects.filter(created_at__lt=border):
        if job.file:
            job.file.delete(save=False)
        job.delete()
        removed += 1
    return removed
