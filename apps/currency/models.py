from django.conf import settings
from django.db import models

from core.models import TimeStampedModel

QUOTE_CODE = "UZS"  # kurslar so'mda ifodalanadi: 1 birlik valyuta = rate UZS


class Currency(TimeStampedModel):
    code = models.CharField(max_length=3, unique=True)
    name = models.CharField(max_length=50)
    symbol = models.CharField(max_length=10, blank=True)
    decimal_places = models.PositiveSmallIntegerField(default=2)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "code"]
        verbose_name_plural = "currencies"

    def __str__(self):
        return self.code

    @property
    def is_quote(self) -> bool:
        return self.code == QUOTE_CODE


class ExchangeRate(models.Model):
    class Source(models.TextChoices):
        CBU = "cbu", "Markaziy bank"
        MANUAL = "manual", "Qo'lda"

    currency = models.ForeignKey(Currency, on_delete=models.CASCADE, related_name="rates")
    rate = models.DecimalField(max_digits=20, decimal_places=6)
    date = models.DateField()
    source = models.CharField(max_length=20, choices=Source.choices)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # bir kunga bitta kurs: qo'lda kiritilgan CBU nikini almashtiradi
        constraints = [
            models.UniqueConstraint(fields=["currency", "date"], name="uniq_rate_currency_date")
        ]
        indexes = [models.Index(fields=["currency", "-date"])]
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"{self.currency_id}: {self.rate} ({self.date})"
