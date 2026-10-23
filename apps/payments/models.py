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
    is_manual = models.BooleanField(
        default=False, help_text="Kassaga qo'lda kiritiladimi (kiritish, inkassatsiya, xarajat)"
    )

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


class Customer(TimeStampedModel):
    """Mijoz (barcha nuqtalar uchun umumiy). Qarzlari nuqta bo'yicha, balans — hammasi bo'yicha."""

    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=30, blank=True, db_index=True)
    tin = models.CharField(max_length=20, blank=True, help_text="STIR / JSHSHIR")
    address = models.CharField(max_length=255, blank=True)
    note = models.TextField(blank=True)
    credit_limit_base = models.DecimalField(
        max_digits=20,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Asosiy valyutada; null — sozlamadagi default",
    )
    default_due_days = models.PositiveIntegerField(
        null=True, blank=True, help_text="null — sozlamadagi default"
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name", "id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(credit_limit_base__isnull=True) | Q(credit_limit_base__gte=0),
                name="customer_credit_limit_gte_0",
            )
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
    customer = models.ForeignKey(
        Customer, null=True, blank=True, on_delete=models.PROTECT, related_name="payments"
    )
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


class CashShift(models.Model):
    """Kassa smenasi (nuqta bo'yicha, barcha valyutalar); ochiq smenada yozuvlar unga bog'lanadi."""

    class Status(models.TextChoices):
        OPEN = "open", "Ochiq"
        CLOSED = "closed", "Yopilgan"

    branch = models.ForeignKey("branches.Branch", on_delete=models.PROTECT, related_name="+")
    status = models.CharField(max_length=6, choices=Status.choices, default=Status.OPEN)
    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    opened_at = models.DateTimeField()
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    closed_at = models.DateTimeField(null=True, blank=True)
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-opened_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["branch"], condition=Q(status="open"), name="one_open_shift_per_branch"
            )
        ]

    def __str__(self):
        return f"Smena #{self.pk}"


class CashShiftBalance(models.Model):
    """Smenadagi har valyuta kassasi: ochilishdagi qoldiq, yopilishda kutilgan va sanalgan."""

    shift = models.ForeignKey(CashShift, on_delete=models.CASCADE, related_name="balances")
    cashbox = models.ForeignKey("Cashbox", on_delete=models.PROTECT, related_name="+")
    opening_balance = models.DecimalField(max_digits=20, decimal_places=4)
    expected_balance = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    actual_balance = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    difference = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)

    class Meta:
        ordering = ["cashbox_id"]
        constraints = [
            models.UniqueConstraint(fields=["shift", "cashbox"], name="shift_cashbox_uniq")
        ]

    def __str__(self):
        return f"{self.shift_id}:{self.cashbox_id}"


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
    shift = models.ForeignKey(
        CashShift, null=True, blank=True, on_delete=models.PROTECT, related_name="transactions"
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


class Debt(models.Model):
    """Nasiya qarzi — savdo valyutasida qoladi (USD qarz USD da).

    Qoldiq = amount - paid_amount - returned_amount (qaytarilgan tovar qarzdan ayiriladi).
    """

    class Status(models.TextChoices):
        OPEN = "open", "Ochiq"
        PAID = "paid", "To'langan"
        CANCELLED = "cancelled", "Bekor qilingan"

    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="debts")
    branch = models.ForeignKey("branches.Branch", on_delete=models.PROTECT, related_name="+")
    currency = models.ForeignKey("currency.Currency", on_delete=models.PROTECT, related_name="+")
    amount = models.DecimalField(max_digits=20, decimal_places=4)
    paid_amount = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    returned_amount = models.DecimalField(
        max_digits=20, decimal_places=4, default=0, help_text="qaytarilgan tovar summasi"
    )
    due_date = models.DateField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    # hujjat (savdo): FK emas — payments savdoni bilmaydi
    document_type = models.CharField(max_length=30)
    document_id = models.BigIntegerField()
    document_number = models.CharField(max_length=40, blank=True)
    overdue_notified_at = models.DateTimeField(null=True, blank=True)
    settled_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["due_date", "id"]
        indexes = [
            models.Index(fields=["customer", "status"]),
            models.Index(fields=["status", "due_date"]),
            models.Index(fields=["document_type", "document_id"]),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="debt_amount_gt_0"),
            models.CheckConstraint(
                condition=Q(paid_amount__gte=0)
                & Q(returned_amount__gte=0)
                & Q(paid_amount__lte=models.F("amount") - models.F("returned_amount")),
                name="debt_paid_returned_within_amount",
            ),
        ]

    def __str__(self):
        return f"Qarz #{self.pk} ({self.customer_id})"

    @property
    def remaining(self):
        return self.amount - self.paid_amount - self.returned_amount


class DebtAllocation(models.Model):
    """To'lovning qaysi qarzga qancha tushgani (qarz valyutasida)."""

    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name="allocations")
    debt = models.ForeignKey(Debt, on_delete=models.PROTECT, related_name="allocations")
    amount = models.DecimalField(max_digits=20, decimal_places=4, help_text="qarz valyutasida")
    payment_amount = models.DecimalField(
        max_digits=20, decimal_places=4, help_text="to'lov valyutasida"
    )

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="debt_alloc_amount_gt_0"),
        ]

    def __str__(self):
        return f"{self.payment_id}→{self.debt_id}: {self.amount}"


class CustomerLedgerEntry(models.Model):
    """Mijoz hisobi (akt-sverka) — faqat INSERT. amount ishorali: qarz +, to'lov −.

    balance_after — shu mijoz × valyuta bo'yicha qarz qoldig'i.
    """

    class Type(models.TextChoices):
        DEBT = "debt", "Nasiya"
        PAYMENT = "payment", "To'lov"
        REFUND = "refund", "To'lov qaytarildi"
        CANCEL = "cancel", "Qarz bekor qilindi"
        RETURN = "return", "Tovar qaytarildi"

    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="ledger")
    currency = models.ForeignKey("currency.Currency", on_delete=models.PROTECT, related_name="+")
    type = models.CharField(max_length=10, choices=Type.choices)
    amount = models.DecimalField(max_digits=20, decimal_places=4)
    balance_after = models.DecimalField(max_digits=20, decimal_places=4)
    debt = models.ForeignKey(
        Debt, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    payment = models.ForeignKey(
        Payment, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    document_type = models.CharField(max_length=30, blank=True)
    document_id = models.BigIntegerField(null=True, blank=True)
    document_number = models.CharField(max_length=40, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["customer", "currency", "-created_at"])]

    def __str__(self):
        return f"{self.customer_id} {self.type} {self.amount}"
