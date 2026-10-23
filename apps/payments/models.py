from django.conf import settings
from django.db import models
from django.db.models import Q

from core.models import TimeStampedModel

from .types import Direction, PaymentKind


class PaymentMethod(TimeStampedModel):
    """To'lov turi (MB da): naqd, terminal, o'tkazma; keyin Click, Payme — provider orqali."""

    code = models.SlugField(max_length=30, unique=True)
    name = models.CharField(max_length=50)
    provider = models.CharField(
        max_length=20, default="manual", help_text="providers registry kaliti"
    )
    is_cash = models.BooleanField(default=False, help_text="Kassa qoldig'iga ta'sir qiladimi")
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "code"]

    def __str__(self):
        return self.name


class CashFlowCategory(models.Model):
    code = models.SlugField(max_length=30, unique=True)
    name = models.CharField(max_length=60)
    direction = models.CharField(max_length=4, default="both", help_text="in | out | both")

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return self.name


class Cashbox(TimeStampedModel):
    """Nuqta × valyuta bo'yicha naqd pul qutisi. Qoldiq — CashTransaction yig'indisi (kesh)."""

    branch = models.ForeignKey("branches.Branch", on_delete=models.PROTECT, related_name="+")
    currency = models.ForeignKey("currency.Currency", on_delete=models.PROTECT, related_name="+")
    name = models.CharField(max_length=60)
    balance = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["branch_id", "currency_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["branch", "currency"], name="cashbox_branch_currency_uniq"
            ),
            models.CheckConstraint(condition=Q(balance__gte=0), name="cashbox_balance_gte_0"),
        ]

    def __str__(self):
        return self.name


class Payment(models.Model):
    class Status(models.TextChoices):
        COMPLETED = "completed", "Bajarildi"
        REVERSED = "reversed", "Qaytarildi"

    number = models.CharField(max_length=40, unique=True)
    branch = models.ForeignKey("branches.Branch", on_delete=models.PROTECT, related_name="+")
    method = models.ForeignKey(PaymentMethod, on_delete=models.PROTECT, related_name="payments")
    kind = models.CharField(max_length=20, choices=PaymentKind.choices)
    direction = models.CharField(max_length=3, choices=Direction.choices)
    currency = models.ForeignKey("currency.Currency", on_delete=models.PROTECT, related_name="+")
    amount = models.DecimalField(max_digits=20, decimal_places=4)
    rate_to_base = models.DecimalField(max_digits=24, decimal_places=12)
    amount_base = models.DecimalField(max_digits=20, decimal_places=4)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.COMPLETED)
    reversal_of = models.OneToOneField(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="reversal"
    )
    provider_reference = models.CharField(max_length=100, blank=True)
    # hujjat (savdo, keyin qarz to'lovi): FK emas — payments boshqa app modellarini bilmaydi
    document_type = models.CharField(max_length=30)
    document_id = models.BigIntegerField()
    document_number = models.CharField(max_length=40, blank=True)
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    received_at = models.DateTimeField()
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-received_at", "-id"]
        indexes = [
            models.Index(fields=["document_type", "document_id"]),
            models.Index(fields=["branch", "-received_at"]),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="payment_amount_gt_0")
        ]

    def __str__(self):
        return self.number


class CashTransaction(models.Model):
    """Kassa jurnali — faqat INSERT. balance_after — shu yozuvdan keyingi qoldiq."""

    cashbox = models.ForeignKey(Cashbox, on_delete=models.PROTECT, related_name="transactions")
    direction = models.CharField(max_length=3, choices=Direction.choices)
    category = models.ForeignKey(CashFlowCategory, on_delete=models.PROTECT, related_name="+")
    amount = models.DecimalField(max_digits=20, decimal_places=4)
    balance_after = models.DecimalField(max_digits=20, decimal_places=4)
    payment = models.ForeignKey(
        Payment, null=True, blank=True, on_delete=models.PROTECT, related_name="cash_transactions"
    )
    document_type = models.CharField(max_length=30, blank=True)
    document_id = models.BigIntegerField(null=True, blank=True)
    document_number = models.CharField(max_length=40, blank=True)
    note = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["cashbox", "-created_at"])]
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="cash_tx_amount_gt_0"),
            models.CheckConstraint(condition=Q(balance_after__gte=0), name="cash_tx_balance_gte_0"),
        ]

    def __str__(self):
        return f"{self.cashbox} {self.direction} {self.amount}"
