from django.conf import settings
from django.db import models


def report_upload_to(job, filename: str) -> str:
    return f"reports/{job.created_at:%Y/%m}/{filename}"


class ReportJob(models.Model):
    """Fonda (Celery) tayyorlanadigan hisobot fayli. Faqat so'ragan foydalanuvchi yuklab oladi."""

    class Status(models.TextChoices):
        PENDING = "pending", "Navbatda"
        RUNNING = "running", "Tayyorlanmoqda"
        READY = "ready", "Tayyor"
        FAILED = "failed", "Xato"

    report_key = models.CharField(max_length=50)
    title = models.CharField(max_length=200)
    params = models.JSONField(default=dict)
    format = models.CharField(max_length=10)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    file = models.FileField(upload_to=report_upload_to, blank=True)
    rows_count = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["requested_by", "-created_at"])]

    def __str__(self):
        return f"{self.report_key}.{self.format} #{self.pk} ({self.status})"
