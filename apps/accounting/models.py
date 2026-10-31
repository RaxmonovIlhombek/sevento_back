from django.db import models

from core.models import TimeStampedModel


class Account(TimeStampedModel):
    """Hisoblar rejasi (Chart of Accounts)."""

    class Type(models.TextChoices):
        ASSET = "asset", "Aktiv"
        LIABILITY = "liability", "Passiv"
        EQUITY = "equity", "Kapital"
        INCOME = "income", "Daromad"
        EXPENSE = "expense", "Xarajat"

    class NormalBalance(models.TextChoices):
        DEBIT = "debit", "Debet"
        CREDIT = "credit", "Kredit"

    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=200)
    account_type = models.CharField(max_length=12, choices=Type.choices)
    normal_balance = models.CharField(
        max_length=6, choices=NormalBalance.choices, default=NormalBalance.DEBIT
    )
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="children"
    )
    is_active = models.BooleanField(default=True)
    is_postable = models.BooleanField(default=True, help_text="Faqat barg (leaf) hisoblar ga yozuv mumkin")
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["code"]
        indexes = [models.Index(fields=["account_type", "is_active"])]

    def __str__(self):
        return f"{self.code} — {self.name}"

    @property
    def is_debit_normal(self):
        return self.normal_balance == self.NormalBalance.DEBIT


class FiscalYear(TimeStampedModel):
    year = models.PositiveSmallIntegerField(unique=True)
    start_date = models.DateField()
    end_date = models.DateField()
    is_closed = models.BooleanField(default=False)

    class Meta:
        ordering = ["-year"]

    def __str__(self):
        return str(self.year)


class FiscalPeriod(TimeStampedModel):
    fiscal_year = models.ForeignKey(FiscalYear, on_delete=models.PROTECT, related_name="periods")
    number = models.PositiveSmallIntegerField()
    start_date = models.DateField()
    end_date = models.DateField()
    is_closed = models.BooleanField(default=False)

    class Meta:
        ordering = ["fiscal_year__year", "number"]
        constraints = [
            models.UniqueConstraint(
                fields=["fiscal_year", "number"], name="uniq_fiscal_period"
            )
        ]

    def __str__(self):
        return f"{self.fiscal_year.year}-{self.number:02d}"


class JournalEntry(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Qoralama"
        POSTED = "posted", "O'tkazildi"
        REVERSED = "reversed", "Bekor qilindi"

    number = models.CharField(max_length=40, unique=True)
    date = models.DateField()
    fiscal_period = models.ForeignKey(
        FiscalPeriod, on_delete=models.PROTECT, related_name="entries"
    )
    branch = models.ForeignKey(
        "branches.Branch", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    description = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    posted_at = models.DateTimeField(null=True, blank=True)
    posted_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    reversed_by_entry = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="reversals"
    )
    created_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        ordering = ["-date", "-id"]
        indexes = [models.Index(fields=["branch", "-date"]), models.Index(fields=["status"])]

    def __str__(self):
        return self.number


class JournalLine(models.Model):
    entry = models.ForeignKey(JournalEntry, on_delete=models.CASCADE, related_name="lines")
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="lines")
    description = models.CharField(max_length=255, blank=True)
    debit = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    credit = models.DecimalField(max_digits=20, decimal_places=4, default=0)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(condition=models.Q(debit__gte=0), name="jl_debit_gte_0"),
            models.CheckConstraint(condition=models.Q(credit__gte=0), name="jl_credit_gte_0"),
        ]

    def __str__(self):
        return f"{self.account.code}: D{self.debit} C{self.credit}"
