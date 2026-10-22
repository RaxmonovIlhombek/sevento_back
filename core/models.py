from django.conf import settings
from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class OutboxEvent(models.Model):
    """Domen hodisasi — tranzaksiya ichida yoziladi, commit dan keyin tarqatiladi."""

    class Status(models.TextChoices):
        PENDING = "pending", "Kutilmoqda"
        DISPATCHED = "dispatched", "Tarqatildi"
        FAILED = "failed", "Xato"

    name = models.CharField(max_length=100, db_index=True)
    aggregate_type = models.CharField(max_length=50, blank=True)
    aggregate_id = models.BigIntegerField(null=True, blank=True)
    payload = models.JSONField(default=dict)
    actor_id = models.BigIntegerField(null=True, blank=True)
    branch_id = models.BigIntegerField(null=True, blank=True)
    request_id = models.CharField(max_length=64, blank=True)
    ip = models.CharField(max_length=45, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.TextField(blank=True)
    occurred_at = models.DateTimeField()
    dispatched_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["status", "created_at"])]
        ordering = ["id"]

    def __str__(self):
        return f"{self.name}#{self.pk} ({self.status})"


class SystemSetting(TimeStampedModel):
    """O'zgaruvchan biznes sozlamalari (kod emas, MB). Ta'riflar core.settings_registry da."""

    key = models.CharField(max_length=100, unique=True)
    value = models.JSONField()
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["key"]

    def __str__(self):
        return self.key


class DocumentSequence(models.Model):
    """Hujjat raqamlari: tur + nuqta + yil bo'yicha ketma-ket."""

    doc_type = models.CharField(max_length=10)
    branch_id = models.BigIntegerField()
    year = models.PositiveSmallIntegerField()
    last_number = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["doc_type", "branch_id", "year"], name="uniq_document_sequence"
            )
        ]

    def __str__(self):
        return f"{self.doc_type}/{self.branch_id}/{self.year}: {self.last_number}"


class IdempotencyRecord(models.Model):
    """Idempotency-Key bilan kelgan so'rov javobi; takroriy so'rovga shu javob qaytariladi."""

    key = models.CharField(max_length=128)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    method = models.CharField(max_length=10)
    path = models.CharField(max_length=255)
    response_status = models.PositiveSmallIntegerField(null=True, blank=True)
    response_body = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["key", "user"], name="uniq_idempotency_key_user")
        ]

    def __str__(self):
        return f"{self.key} ({self.method} {self.path})"
