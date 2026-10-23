from celery import shared_task

from . import services


@shared_task(name="reports.generate_report")
def generate_report(job_id: int) -> str:
    """Og'ir hisobot fayli (PDF/Excel); tayyor bo'lsa report.ready → user_{id}."""
    return services.run_job(job_id).status


@shared_task(name="reports.cleanup_report_files")
def cleanup_report_files() -> int:
    """Celery Beat (default har kuni 03:20): saqlash muddati o'tgan fayllar."""
    return services.cleanup_old_jobs()
