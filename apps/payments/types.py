"""Boshqa app lar import qiladigan oddiy turlar (models emas)."""

from dataclasses import dataclass

from django.db import models


class Direction(models.TextChoices):
    IN = "in", "Kirim"
    OUT = "out", "Chiqim"


class PaymentKind(models.TextChoices):
    PAYMENT = "payment", "To'lov"
    CHANGE = "change", "Qaytim"
    REFUND = "refund", "Pul qaytarildi"
    CHANGE_RETURN = "change_return", "Qaytim qaytarildi"


@dataclass(frozen=True)
class PaymentDoc:
    """To'lov qaysi hujjatga tegishli (savdo, keyin qarz to'lovi, ...)."""

    type: str
    id: int
    number: str = ""
