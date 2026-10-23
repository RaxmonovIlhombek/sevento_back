"""Hisobot testlari uchun oqim: kirim → savdo (naqd, nasiya) → qaytarish → hisobdan chiqarish."""

from decimal import Decimal

import pytest
from django.db import transaction

from apps.catalog import services as catalog_services
from apps.catalog.models import PriceType, Product, Unit
from apps.currency import services as currency_services
from apps.currency.models import Currency
from apps.inventory import services as inventory_services
from apps.inventory.models import WriteOffReason
from apps.payments.models import Customer, PaymentMethod
from apps.purchasing import services as purchasing_services
from apps.purchasing.models import Supplier
from apps.sales import services as sales_services

D = Decimal


@pytest.fixture(autouse=True)
def _media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path


@pytest.fixture
def world(owner, branch, roles):
    """USD kursi 12 500. Cola (so'mda 10 000), kirim 20 dona × 0,40 USD.

    Savdolar: S1 — 5 dona naqd (50 000), S2 — 3 dona nasiya (30 000, mijoz). S1 dan 1 dona qaytdi.
    Hisobdan chiqarish: 2 dona (buzilgan).
    """
    usd = Currency.objects.get(code="USD")
    uzs = Currency.objects.get(code="UZS")
    currency_services.set_rate(actor=owner, currency=usd, rate=D("12500"))
    retail = PriceType.objects.get(is_default=True)
    dona = Unit.objects.get(code="dona")
    cola = Product.objects.create(sku="COLA", name="Cola 1L", unit=dona)
    catalog_services.set_price(
        actor=owner, product=cola, price_type=retail, currency=uzs, amount=D("10000")
    )
    supplier = Supplier.objects.create(name="Ta'minotchi")
    purchase = purchasing_services.create_purchase(
        actor=owner,
        branch=branch,
        supplier=supplier,
        currency=usd,
        items=[{"product": cola, "quantity": D("20"), "unit_price": D("0.40")}],
    )
    purchasing_services.receive_purchase(actor=owner, purchase=purchase)
    cash = PaymentMethod.objects.get(code="cash")
    customer = Customer.objects.create(name="Aliyev Vali", credit_limit_base=D("100"))
    with transaction.atomic():
        s1 = sales_services.create_sale(
            actor=owner,
            branch=branch,
            currency=uzs,
            items=[{"product": cola, "quantity": D("5")}],
            payments=[{"method": cash, "currency": uzs, "amount": D("50000")}],
        )
        s2 = sales_services.create_sale(
            actor=owner,
            branch=branch,
            currency=uzs,
            items=[{"product": cola, "quantity": D("3")}],
            payments=[],
            customer=customer,
        )
        sales_services.create_return(
            actor=owner,
            sale=s1,
            items=[{"sale_item": s1.items.get().pk, "quantity": D("1")}],
            reason="Sifatsiz",
        )
        inventory_services.create_write_off(
            actor=owner,
            branch=branch,
            reason=WriteOffReason.objects.get(code="damaged"),
            items=[{"product": cola, "quantity": D("2")}],
        )
    return {"cola": cola, "uzs": uzs, "usd": usd, "s1": s1, "s2": s2, "customer": customer}
