"""Qoldiq, partiyalar va harakatlar jurnali.

Inventory boshqa hujjat app lariga (purchasing, sales, ...) bog'lanmaydi: manba hujjat
`source_type/source_id/source_line_id` (partiya) va `document_type/document_id` (harakat) orqali.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import TimeStampedModel

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


# --- 7-bosqich: ko'chirish, inventarizatsiya, hisobdan chiqarish ---


class Transfer(TimeStampedModel):
    """Nuqtalar orasida ko'chirish: qoralama → jo'natildi → qabul qilindi (yoki bekor)."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Qoralama"
        SENT = "sent", "Jo'natildi"
        RECEIVED = "received", "Qabul qilindi"
        CANCELLED = "cancelled", "Bekor qilindi"

    number = models.CharField(max_length=50, unique=True)
    from_branch = models.ForeignKey("branches.Branch", on_delete=models.PROTECT, related_name="+")
    to_branch = models.ForeignKey("branches.Branch", on_delete=models.PROTECT, related_name="+")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    note = models.TextField(blank=True)
    # jo'natilgandagi FIFO tannarx va qabulda yetishmagan qismi (asosiy valyutada)
    total_cost_base = models.DecimalField(default=0, **MONEY)
    shortage_cost_base = models.DecimalField(default=0, **MONEY)
    has_discrepancy = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    sent_at = models.DateTimeField(null=True, blank=True)
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    received_at = models.DateTimeField(null=True, blank=True)
    receive_note = models.TextField(blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["from_branch", "status", "-created_at"]),
            models.Index(fields=["to_branch", "status", "-created_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(from_branch=models.F("to_branch")),
                name="transfer_branches_differ",
            ),
        ]

    def __str__(self):
        return self.number


class TransferItem(models.Model):
    transfer = models.ForeignKey(Transfer, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT, related_name="+")
    position = models.PositiveIntegerField(default=0)
    quantity = models.DecimalField(**QTY)  # jo'natiladigan miqdor
    quantity_received = models.DecimalField(null=True, blank=True, **QTY)
    unit_cost_base = models.DecimalField(default=0, **UNIT_COST)  # o'rtacha (FIFO partiyalardan)
    total_cost_base = models.DecimalField(default=0, **MONEY)
    # jo'natishda FIFO: [{batch_id, quantity, unit_cost_base}] — bekor qilish va qabul shu bo'yicha
    batch_allocations = models.JSONField(default=list)

    class Meta:
        ordering = ["position", "id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0), name="transfer_item_qty_positive"
            ),
            models.CheckConstraint(
                condition=models.Q(quantity_received__gte=0)
                & models.Q(quantity_received__lte=models.F("quantity"))
                | models.Q(quantity_received__isnull=True),
                name="transfer_item_received_range",
            ),
        ]

    def __str__(self):
        return f"{self.transfer_id}: {self.product_id} × {self.quantity}"

    @property
    def shortage(self):
        if self.quantity_received is None:
            return self.quantity * 0
        return self.quantity - self.quantity_received


class StockCount(TimeStampedModel):
    """Inventarizatsiya: sanash (qoralama) → yakunlash (farq ortiqcha/kamomad harakatlari)."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Sanalmoqda"
        COMPLETED = "completed", "Yakunlandi"
        CANCELLED = "cancelled", "Bekor qilindi"

    number = models.CharField(max_length=50, unique=True)
    branch = models.ForeignKey("branches.Branch", on_delete=models.PROTECT, related_name="+")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    category = models.ForeignKey(
        "catalog.Category", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    note = models.TextField(blank=True)
    surplus_cost_base = models.DecimalField(default=0, **MONEY)
    shortage_cost_base = models.DecimalField(default=0, **MONEY)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["branch", "status", "-created_at"])]
        constraints = [
            # bir nuqtada bir vaqtda bitta ochiq inventarizatsiya
            models.UniqueConstraint(
                fields=["branch"],
                condition=models.Q(status="draft"),
                name="uniq_open_count_per_branch",
            ),
        ]

    def __str__(self):
        return self.number


class StockCountItem(models.Model):
    count = models.ForeignKey(StockCount, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT, related_name="+")
    # hisobdagi qoldiq: yaratilganda olinadi, yakunlashda joriy qoldiq bilan yangilanadi
    expected_quantity = models.DecimalField(default=0, **QTY)
    counted_quantity = models.DecimalField(null=True, blank=True, **QTY)  # bo'sh — sanalmagan
    difference = models.DecimalField(default=0, **QTY)  # yakunlashda: counted - expected
    unit_cost_base = models.DecimalField(default=0, **UNIT_COST)
    cost_difference_base = models.DecimalField(default=0, **MONEY)

    class Meta:
        ordering = ["product__name", "id"]
        constraints = [
            models.UniqueConstraint(fields=["count", "product"], name="uniq_count_product"),
            models.CheckConstraint(
                condition=models.Q(counted_quantity__gte=0)
                | models.Q(counted_quantity__isnull=True),
                name="count_item_counted_non_negative",
            ),
        ]

    def __str__(self):
        return f"{self.count_id}: {self.product_id}"


class WriteOffReason(TimeStampedModel):
    """Hisobdan chiqarish sababi (MB ma'lumotnomasi): buzilgan, muddati o'tgan, yo'qolgan, ..."""

    code = models.CharField(max_length=30, unique=True)
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)
    # tizim sababi (masalan transfer_shortage) — qo'lda tanlanmaydi
    is_system = models.BooleanField(default=False)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class WriteOff(TimeStampedModel):
    """Hisobdan chiqarish: yaratilishi bilan yakunlanadi (FIFO chiqim); bekor — asl partiyalarga."""

    class Status(models.TextChoices):
        COMPLETED = "completed", "Yakunlandi"
        CANCELLED = "cancelled", "Bekor qilindi"

    number = models.CharField(max_length=50, unique=True)
    branch = models.ForeignKey("branches.Branch", on_delete=models.PROTECT, related_name="+")
    reason = models.ForeignKey(WriteOffReason, on_delete=models.PROTECT, related_name="+")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.COMPLETED)
    note = models.TextField(blank=True)
    total_cost_base = models.DecimalField(default=0, **MONEY)
    # ko'chirishda yo'qolgan tovar uchun avtomatik hujjat (qoldiqqa ta'sir qilmaydi)
    transfer = models.ForeignKey(
        Transfer, null=True, blank=True, on_delete=models.PROTECT, related_name="write_offs"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    completed_at = models.DateTimeField(default=timezone.now)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-completed_at", "-id"]
        indexes = [models.Index(fields=["branch", "status", "-completed_at"])]

    def __str__(self):
        return self.number


class WriteOffItem(models.Model):
    write_off = models.ForeignKey(WriteOff, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT, related_name="+")
    position = models.PositiveIntegerField(default=0)
    quantity = models.DecimalField(**QTY)
    unit_cost_base = models.DecimalField(default=0, **UNIT_COST)
    total_cost_base = models.DecimalField(default=0, **MONEY)
    batch_allocations = models.JSONField(default=list)

    class Meta:
        ordering = ["position", "id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0), name="write_off_item_qty_positive"
            ),
        ]

    def __str__(self):
        return f"{self.write_off_id}: {self.product_id} × {self.quantity}"
