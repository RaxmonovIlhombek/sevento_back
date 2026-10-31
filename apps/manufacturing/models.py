from django.conf import settings
from django.db import models

from core.models import TimeStampedModel


class BillOfMaterials(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Qoralama"
        ACTIVE = "active", "Faol"
        ARCHIVED = "archived", "Arxivlangan"

    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT, related_name="boms")
    name = models.CharField(max_length=200)
    version = models.CharField(max_length=20, default="1.0")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    quantity = models.DecimalField(max_digits=14, decimal_places=3, default=1, help_text="Tayyor mahsulot miqdori")
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["product", "version"], name="uniq_bom_product_version")
        ]

    def __str__(self):
        return f"{self.product} — v{self.version}"


class BOMItem(TimeStampedModel):
    bom = models.ForeignKey(BillOfMaterials, on_delete=models.CASCADE, related_name="items")
    component = models.ForeignKey("catalog.Product", on_delete=models.PROTECT, related_name="bom_usages")
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    unit = models.ForeignKey("catalog.Unit", on_delete=models.PROTECT, related_name="+")
    scrap_rate = models.DecimalField(max_digits=6, decimal_places=4, default=0, help_text="Brak foizi")

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.component} × {self.quantity}"


class ProductionOrder(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Qoralama"
        RELEASED = "released", "Ishga tushirildi"
        IN_PROGRESS = "in_progress", "Jarayonda"
        COMPLETED = "completed", "Yakunlandi"
        CANCELLED = "cancelled", "Bekor qilindi"

    number = models.CharField(max_length=40, unique=True)
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT, related_name="production_orders")
    bom = models.ForeignKey(BillOfMaterials, on_delete=models.PROTECT, related_name="production_orders")
    branch = models.ForeignKey("branches.Branch", on_delete=models.PROTECT, related_name="+")
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    planned_start = models.DateField(null=True, blank=True)
    planned_end = models.DateField(null=True, blank=True)
    actual_start = models.DateTimeField(null=True, blank=True)
    actual_end = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.number
