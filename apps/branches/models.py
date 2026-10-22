from django.db import models

from core.models import TimeStampedModel


class Branch(TimeStampedModel):
    class Type(models.TextChoices):
        SHOP = "shop", "Do'kon"
        WAREHOUSE = "warehouse", "Ombor"

    code = models.CharField(max_length=10, unique=True, help_text="Hujjat raqamlarida ishlatiladi")
    name = models.CharField(max_length=100)
    type = models.CharField(max_length=20, choices=Type.choices, default=Type.SHOP)
    address = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    settings = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "branches"

    def __str__(self):
        return f"{self.name} ({self.code})"
