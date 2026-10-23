from django.conf import settings
from django.db import models
from django.db.models import Q

from core.models import TimeStampedModel


class Sale(TimeStampedModel):
    """Savdo: to'liq to'lov yoki qisman/to'liq nasiya (mijoz bilan, kredit limiti doirasida)."""

    class Status(models.TextChoices):
        COMPLETED = "completed", "Yakunlandi"
        CANCELLED = "cancelled", "Bekor qilindi"

    number = models.CharField(max_length=40, unique=True)
    branch = models.ForeignKey("branches.Branch", on_delete=models.PROTECT, related_name="+")
    seller = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    price_type = models.ForeignKey("catalog.PriceType", on_delete=models.PROTECT, related_name="+")
    customer = models.ForeignKey(
        "payments.Customer", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
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
    debt_amount = models.DecimalField(
        max_digits=20, decimal_places=4, default=0, help_text="nasiya (savdo valyutasida)"
    )
    due_date = models.DateField(null=True, blank=True)
    # qaytarishlar yig'indisi (savdo valyutasida / asosiy valyutada / FIFO tannarx)
    returned_total = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    returned_total_base = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    returned_cost_base = models.DecimalField(max_digits=20, decimal_places=4, default=0)
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
        """Yalpi foyda (asosiy valyutada), qaytarishlar ayirilgan. Bekor qilingan savdoda 0."""
        if self.status != self.Status.COMPLETED:
            return self.total_base * 0
        return (self.total_base - self.returned_total_base) - (
            self.cost_base - self.returned_cost_base
        )

    @property
    def return_state(self) -> str:
        """none | partial | full — ro'yxatda belgi uchun."""
        if self.returned_total <= 0:
            return "none"
        return "full" if self.returned_total >= self.total else "partial"


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
    returned_quantity = models.DecimalField(max_digits=14, decimal_places=3, default=0)

    class Meta:
        ordering = ["position", "id"]
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0), name="sale_item_qty_gt_0"),
            models.CheckConstraint(
                condition=Q(discount_amount__gte=0), name="sale_item_discount_gte_0"
            ),
            models.CheckConstraint(
                condition=Q(returned_quantity__gte=0)
                & Q(returned_quantity__lte=models.F("quantity")),
                name="sale_item_returned_within_quantity",
            ),
        ]

    def __str__(self):
        return f"{self.sale_id}:{self.position}"


class SaleReturn(TimeStampedModel):
    """Savdo qaytarish: tovar asl partiyalarga, summa avval nasiya qarzidan ayiriladi, qolgani
    mijozga pul bilan qaytariladi (default — naqd, kassadan)."""

    number = models.CharField(max_length=40, unique=True)
    sale = models.ForeignKey(Sale, on_delete=models.PROTECT, related_name="returns")
    branch = models.ForeignKey("branches.Branch", on_delete=models.PROTECT, related_name="+")
    customer = models.ForeignKey(
        "payments.Customer", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    currency = models.ForeignKey("currency.Currency", on_delete=models.PROTECT, related_name="+")
    total = models.DecimalField(max_digits=20, decimal_places=4, help_text="savdo valyutasida")
    total_base = models.DecimalField(
        max_digits=20, decimal_places=4, help_text="savdo kursi bilan (foyda hisobi uchun)"
    )
    cost_base = models.DecimalField(max_digits=20, decimal_places=4)
    debt_reduction = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    refund_amount = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    refund_method = models.ForeignKey(
        "payments.PaymentMethod", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    reason = models.CharField(max_length=255)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["branch", "-created_at"])]
        constraints = [
            models.CheckConstraint(condition=Q(total__gte=0), name="sale_return_total_gte_0"),
        ]

    def __str__(self):
        return self.number


class SaleReturnItem(models.Model):
    sale_return = models.ForeignKey(SaleReturn, on_delete=models.CASCADE, related_name="items")
    sale_item = models.ForeignKey(SaleItem, on_delete=models.PROTECT, related_name="returns")
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT, related_name="+")
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    amount = models.DecimalField(max_digits=20, decimal_places=4, help_text="savdo valyutasida")
    cost_base = models.DecimalField(max_digits=20, decimal_places=4)
    batch_allocations = models.JSONField(default=list)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0), name="sale_return_item_qty_gt_0"),
        ]

    def __str__(self):
        return f"{self.sale_return_id}: {self.product_id} × {self.quantity}"
