from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import TimeStampedModel


class Category(TimeStampedModel):
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="children"
    )
    name = models.CharField(max_length=100)
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name_plural = "categories"
        constraints = [
            models.UniqueConstraint(
                fields=["parent", "name"], name="uniq_category_parent_name", nulls_distinct=False
            )
        ]

    def __str__(self):
        return self.name


class Unit(TimeStampedModel):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=50)
    decimal_places = models.PositiveSmallIntegerField(default=0)  # 0 = faqat butun (dona)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Product(TimeStampedModel):
    sku = models.CharField(max_length=50, unique=True)
    barcode = models.CharField(max_length=64, blank=True, db_index=True)
    name = models.CharField(max_length=200)
    category = models.ForeignKey(
        Category, null=True, blank=True, on_delete=models.PROTECT, related_name="products"
    )
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name="products")
    min_quantity = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        null=True,
        blank=True,
        help_text="Bo'sh — sozlamadagi default (inventory.default_min_quantity)",
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["barcode"], condition=~models.Q(barcode=""), name="uniq_product_barcode"
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.sku})"


class PriceType(TimeStampedModel):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=50)
    is_default = models.BooleanField(default=False)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "code"]

    def __str__(self):
        return self.name


class ProductPrice(models.Model):
    """Narx tarixi: har o'zgarish yangi qator. Joriy narx — eng so'nggi valid_from <= now.

    branch=null — barcha nuqtalar uchun; nuqtaga xos narx umumiyni almashtiradi.
    """

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="prices")
    price_type = models.ForeignKey(PriceType, on_delete=models.PROTECT, related_name="+")
    currency = models.ForeignKey("currency.Currency", on_delete=models.PROTECT, related_name="+")
    branch = models.ForeignKey(
        "branches.Branch", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    amount = models.DecimalField(max_digits=20, decimal_places=4)
    valid_from = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-valid_from", "-id"]
        indexes = [
            models.Index(fields=["product", "price_type", "currency", "branch", "-valid_from"])
        ]

    def __str__(self):
        return f"{self.product_id}/{self.price_type_id}: {self.amount} {self.currency_id}"
