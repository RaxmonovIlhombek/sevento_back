"""Qoldiq, partiyalar va harakatlar jurnali.

Inventory boshqa hujjat app lariga (purchasing, sales, ...) bog'lanmaydi: manba hujjat
`source_type/source_id/source_line_id` (partiya) va `document_type/document_id` (harakat) orqali.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone

from .types import MovementType

QTY = {"max_digits": 14, "decimal_places": 3}
UNIT_COST = {"max_digits": 20, "decimal_places": 6}
MONEY = {"max_digits": 20, "decimal_places": 4}


class StockLevel(models.Model):
    """Nuqta × tovar qoldig'i. Doim SUM(Batch.quantity_remaining) ga teng (invariant, testda)."""

    branch = models.ForeignKey("branches.Branch", on_delete=models.PROTECT, related_name="+")
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT, related_name="+")
    quantity = models.DecimalField(default=0, **QTY)
    min_quantity = models.DecimalField(
        null=True,
        blank=True,
        help_text="Bo'sh — tovardagi yoki sozlamadagi minimal qoldiq",
        **QTY,
    )
    # chegaradan o'tish paytini aniqlash uchun (ogohlantirish har safar emas, bir marta)
    below_minimum = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["branch", "product"], name="uniq_stock_branch_product"),
            models.CheckConstraint(
                condition=models.Q(quantity__gte=0), name="stock_quantity_non_negative"
            ),
        ]

    def __str__(self):
        return f"{self.branch_id}/{self.product_id}: {self.quantity}"


class Batch(models.Model):
    """Partiya: bir kirim qatori (yoki ko'chirish, ortiqcha). FIFO shu jadval bo'yicha."""

    branch = models.ForeignKey("branches.Branch", on_delete=models.PROTECT, related_name="+")
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT, related_name="+")
    source_type = models.CharField(max_length=30)
    source_id = models.BigIntegerField()
    source_line_id = models.BigIntegerField(null=True, blank=True)
    source_number = models.CharField(max_length=50, blank=True)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="children"
    )
    received_at = models.DateTimeField(default=timezone.now)
    quantity_initial = models.DecimalField(**QTY)
    quantity_remaining = models.DecimalField(**QTY)
    unit_cost_base = models.DecimalField(**UNIT_COST)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["received_at", "id"]
        indexes = [
            models.Index(fields=["branch", "product", "received_at", "id"]),
            models.Index(fields=["source_type", "source_id"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity_remaining__gte=0), name="batch_remaining_non_negative"
            ),
            models.CheckConstraint(
                condition=models.Q(quantity_remaining__lte=models.F("quantity_initial")),
                name="batch_remaining_lte_initial",
            ),
        ]

    def __str__(self):
        return f"Partiya #{self.pk} ({self.product_id}: {self.quantity_remaining})"


class StockMovement(models.Model):
    """Ombor harakatlari jurnali (faqat qo'shiladi): har qoldiq o'zgarishi — partiya bo'yicha."""

    branch = models.ForeignKey("branches.Branch", on_delete=models.PROTECT, related_name="+")
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT, related_name="+")
    batch = models.ForeignKey(Batch, on_delete=models.PROTECT, related_name="movements")
    type = models.CharField(max_length=30, choices=MovementType.choices)
    quantity = models.DecimalField(**QTY)  # ishorali: kirim +, chiqim -
    unit_cost_base = models.DecimalField(**UNIT_COST)
    total_cost_base = models.DecimalField(**MONEY)
    balance_after = models.DecimalField(**QTY)
    document_type = models.CharField(max_length=30)
    document_id = models.BigIntegerField()
    document_number = models.CharField(max_length=50, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["branch", "product", "-created_at"]),
            models.Index(fields=["document_type", "document_id"]),
        ]

    def __str__(self):
        return f"{self.type} {self.quantity} ({self.document_type}#{self.document_id})"
