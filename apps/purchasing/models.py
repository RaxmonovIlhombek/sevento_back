from django.conf import settings
from django.db import models

from core.models import TimeStampedModel

QTY = {"max_digits": 14, "decimal_places": 3}
MONEY = {"max_digits": 20, "decimal_places": 4}
UNIT_COST = {"max_digits": 20, "decimal_places": 6}
RATE_TO_BASE = {"max_digits": 24, "decimal_places": 12}


class AllocationMethod(models.TextChoices):
    BY_VALUE = "by_value", "Qiymat bo'yicha"
    BY_QUANTITY = "by_quantity", "Miqdor bo'yicha"


class Supplier(TimeStampedModel):
    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=30, blank=True)
    contact_person = models.CharField(max_length=150, blank=True)
    tin = models.CharField("STIR", max_length=20, blank=True)
    address = models.CharField(max_length=255, blank=True)
    note = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class ExpenseType(TimeStampedModel):
    """Kirimga qo'shimcha xarajat turi (transport, bojxona, yuklash) — MB ma'lumotnomasi."""

    code = models.CharField(max_length=30, unique=True)
    name = models.CharField(max_length=100)
    default_allocation = models.CharField(
        max_length=20, choices=AllocationMethod.choices, default=AllocationMethod.BY_VALUE
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Purchase(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Qoralama"
        RECEIVED = "received", "Qabul qilindi"
        CANCELLED = "cancelled", "Bekor qilindi"

    number = models.CharField(max_length=50, unique=True)
    branch = models.ForeignKey("branches.Branch", on_delete=models.PROTECT, related_name="+")
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="purchases")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    invoice_number = models.CharField(max_length=50, blank=True)
    invoice_date = models.DateField(null=True, blank=True)
    currency = models.ForeignKey("currency.Currency", on_delete=models.PROTECT, related_name="+")
    # qabul qilingan paytdagi snapshot: summa (currency) * rate_to_base = summa (asosiy valyuta)
    rate_to_base = models.DecimalField(null=True, blank=True, **RATE_TO_BASE)
    subtotal = models.DecimalField(default=0, **MONEY)
    subtotal_base = models.DecimalField(default=0, **MONEY)
    expenses_total_base = models.DecimalField(default=0, **MONEY)
    total_base = models.DecimalField(default=0, **MONEY)
    note = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    received_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["branch", "status", "-created_at"])]

    def __str__(self):
        return self.number


class PurchaseItem(models.Model):
    purchase = models.ForeignKey(Purchase, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT, related_name="+")
    position = models.PositiveIntegerField(default=0)
    quantity = models.DecimalField(**QTY)
    unit_price = models.DecimalField(**MONEY)  # kirim valyutasida
    line_total = models.DecimalField(default=0, **MONEY)
    # qabul qilinganda to'ldiriladi (qoralamada — oldindan hisob API da)
    line_total_base = models.DecimalField(default=0, **MONEY)
    allocated_expense_base = models.DecimalField(default=0, **MONEY)
    landed_unit_cost_base = models.DecimalField(default=0, **UNIT_COST)

    class Meta:
        ordering = ["position", "id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0), name="purchase_item_qty_positive"
            ),
            models.CheckConstraint(
                condition=models.Q(unit_price__gte=0), name="purchase_item_price_non_negative"
            ),
        ]

    def __str__(self):
        return f"{self.purchase_id}: {self.product_id} × {self.quantity}"


class PurchaseExpense(models.Model):
    purchase = models.ForeignKey(Purchase, on_delete=models.CASCADE, related_name="expenses")
    expense_type = models.ForeignKey(ExpenseType, on_delete=models.PROTECT, related_name="+")
    currency = models.ForeignKey("currency.Currency", on_delete=models.PROTECT, related_name="+")
    amount = models.DecimalField(**MONEY)
    allocation_method = models.CharField(
        max_length=20, choices=AllocationMethod.choices, default=AllocationMethod.BY_VALUE
    )
    rate_to_base = models.DecimalField(null=True, blank=True, **RATE_TO_BASE)
    amount_base = models.DecimalField(default=0, **MONEY)
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0), name="purchase_expense_amount_positive"
            ),
        ]

    def __str__(self):
        return f"{self.purchase_id}: {self.expense_type_id} {self.amount}"
