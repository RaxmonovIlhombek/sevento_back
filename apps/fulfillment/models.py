from django.conf import settings
from django.db import models

from core.models import TimeStampedModel


class Fulfillment(TimeStampedModel):
    """Sotilgan buyurtmaning yo'li: omborchi → operator → kuryer → mijoz."""

    class Status(models.TextChoices):
        PENDING = "pending", "Omborchi kutmoqda"
        PACKED = "packed", "Taxlandi — operator tekshiradi"
        READY = "ready", "Tayyor — kuryer kutmoqda"
        ON_THE_WAY = "on_the_way", "Yo'lda"
        DELIVERED = "delivered", "Yetkazildi"
        CANCELLED = "cancelled", "Bekor qilindi"

    sale = models.OneToOneField("sales.Sale", on_delete=models.PROTECT, related_name="fulfillment")
    branch = models.ForeignKey("branches.Branch", on_delete=models.PROTECT, related_name="+")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    address = models.CharField(max_length=255, blank=True)
    contact_phone = models.CharField(max_length=30, blank=True)
    note = models.CharField(max_length=255, blank=True)
    # operator qaytargan bo'lsa — oxirgi sabab (omborchi ko'rishi uchun)
    reject_reason = models.CharField(max_length=255, blank=True)

    packed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    packed_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    courier = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    accepted_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    delivered_note = models.CharField(max_length=255, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["branch", "status"])]


class FulfillmentStep(models.Model):
    """Jarayon tarixi: kim, qachon, qaysi holatga o'tkazdi (rahbar va operator kuzatadi)."""

    fulfillment = models.ForeignKey(Fulfillment, on_delete=models.CASCADE, related_name="steps")
    status = models.CharField(max_length=12, choices=Fulfillment.Status.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    note = models.CharField(max_length=255, blank=True)
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["at", "id"]

    def __str__(self):
        return f"{self.fulfillment_id}: {self.status}"
