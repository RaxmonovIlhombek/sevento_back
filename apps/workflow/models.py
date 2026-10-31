from django.conf import settings
from django.db import models

from core.models import TimeStampedModel


class ApprovalRule(TimeStampedModel):
    entity_type = models.CharField(max_length=50, db_index=True)
    min_amount = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    max_amount = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    branch = models.ForeignKey(
        "branches.Branch", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    approver = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    sequence = models.PositiveSmallIntegerField(default=1)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["entity_type", "sequence"]

    def __str__(self):
        return f"{self.entity_type} (seq {self.sequence})"


class ApprovalInstance(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Kutilmoqda"
        APPROVED = "approved", "Tasdiqlandi"
        REJECTED = "rejected", "Rad etildi"
        CANCELLED = "cancelled", "Bekor qilindi"

    entity_type = models.CharField(max_length=50, db_index=True)
    entity_id = models.BigIntegerField(db_index=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    branch = models.ForeignKey(
        "branches.Branch", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    amount = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    decided_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["entity_type", "entity_id"], name="uniq_approval_entity"
            )
        ]

    def __str__(self):
        return f"{self.entity_type}#{self.entity_id} ({self.status})"


class ApprovalStep(TimeStampedModel):
    class Decision(models.TextChoices):
        PENDING = "pending", "Kutilmoqda"
        APPROVED = "approved", "Tasdiqlandi"
        REJECTED = "rejected", "Rad etildi"

    instance = models.ForeignKey(ApprovalInstance, on_delete=models.CASCADE, related_name="steps")
    approver = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    sequence = models.PositiveSmallIntegerField(default=1)
    decision = models.CharField(max_length=10, choices=Decision.choices, default=Decision.PENDING)
    decided_at = models.DateTimeField(null=True, blank=True)
    comment = models.TextField(blank=True)

    class Meta:
        ordering = ["sequence", "id"]

    def __str__(self):
        return f"{self.approver} — {self.decision}"
