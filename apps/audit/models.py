from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """Faqat qo'shiladigan jurnal: har muhim domen hodisasi bitta qator."""

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    branch = models.ForeignKey(
        "branches.Branch", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    event_name = models.CharField(max_length=100, db_index=True)
    aggregate_type = models.CharField(max_length=50, blank=True)
    aggregate_id = models.BigIntegerField(null=True, blank=True)
    payload = models.JSONField(default=dict)
    ip = models.CharField(max_length=45, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)
    request_id = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(db_index=True)

    class Meta:
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["aggregate_type", "aggregate_id"]),
        ]

    def __str__(self):
        return f"{self.event_name} #{self.pk}"
