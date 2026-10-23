from django.conf import settings
from django.db import models
from django.db.models import Q

from core.models import TimeStampedModel


class Sale(TimeStampedModel):
    """Savdo. 5-bosqich: naqd (to'liq to'lov); nasiya va mijoz — 6-bosqichda."""

    class Status(models.TextChoices):
        COMPLETED = "completed", "Yakunlandi"
        CANCELLED = "cancelled", "Bekor qilindi"

    number = models.CharField(max_length=40, unique=True)
    branch = models.ForeignKey("branches.Branch", on_delete=models.PROTECT, related_name="+")
    seller = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    price_type = models.ForeignKey("catalog.PriceType", on_delete=models.PROTECT, related_name="+")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.COMPLETED)
    currency = models.ForeignKey("currency.Currency", on_delete=models.PROTECT, related_name="+")
    rate_to_base = models.DecimalField(max_digits=24, decimal_places=12)
    subtotal = models.DecimalField(max_digits=20, decimal_places=4, help_text="chegirmasiz")
    discount_total = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    total = models.DecimalField(max_digits=20, decimal_places=4)
    total_base = models.DecimalField(max_digits=20, decimal_places=4)
    cost_base = models.DecimalField(max_digits=20, decimal_places=4, help_text="FIFO tannarx")
    paid_total = models.DecimalField(
        max_digits=20, decimal_places=4, help_text="to'lovlar savdo valyutasida"
    )
    change_amount = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    completed_at = models.DateTimeField()
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=255, blank=True)
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-completed_at", "-id"]
        indexes = [models.Index(fields=["branch", "-completed_at"])]
        constraints = [
            models.CheckConstraint(condition=Q(total__gte=0), name="sale_total_gte_0"),
        ]

    def __str__(self):
        return self.number

    @property
    def profit_base(self):
        """Yalpi foyda (asosiy valyutada). Bekor qilingan savdoda 0."""
        if self.status != self.Status.COMPLETED:
            return self.total_base * 0
        return self.total_base - self.cost_base


class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT, related_name="+")
    position = models.PositiveIntegerField(default=0)
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    unit_price = models.DecimalField(max_digits=20, decimal_places=4)
    discount_amount = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    line_total = models.DecimalField(max_digits=20, decimal_places=4)
    cost_base = models.DecimalField(max_digits=20, decimal_places=4)
    # FIFO chiqim: [{batch_id, quantity, unit_cost_base}] — bekor qilishda asl partiyalarga qaytadi
    batch_allocations = models.JSONField(default=list)

    class Meta:
        ordering = ["position", "id"]
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0), name="sale_item_qty_gt_0"),
            models.CheckConstraint(
                condition=Q(discount_amount__gte=0), name="sale_item_discount_gte_0"
            ),
        ]

    def __str__(self):
        return f"{self.sale_id}:{self.position}"
