"""Savdo testlari uchun umumiy ma'lumot: kurs, narxlar, omborda partiyalar."""

from decimal import Decimal

import pytest

from apps.catalog import services as catalog_services
from apps.catalog.models import PriceType, Product, Unit
from apps.currency import services as currency_services
from apps.currency.models import Currency
from apps.inventory import services as inventory_services
from apps.inventory.types import DocRef, MovementType
from apps.payments.models import PaymentMethod

D = Decimal


@pytest.fixture
def usd(db):
    return Currency.objects.get(code="USD")


@pytest.fixture
def uzs(db):
    return Currency.objects.get(code="UZS")


@pytest.fixture
def rate(owner, usd):
    currency_services.set_rate(actor=owner, currency=usd, rate=D("12500"))


@pytest.fixture
def retail(db):
    return PriceType.objects.get(is_default=True)


@pytest.fixture
def cash(db):
    return PaymentMethod.objects.get(code="cash")


@pytest.fixture
def card(db):
    return PaymentMethod.objects.get(code="card")


@pytest.fixture
def products(owner, retail, usd, uzs, rate):
    dona = Unit.objects.get(code="dona")
    kg = Unit.objects.get(code="kg")
    cola = Product.objects.create(sku="COLA", name="Cola 1L", unit=dona, barcode="4780001")
    sugar = Product.objects.create(sku="SUGAR", name="Shakar", unit=kg)
    nopr = Product.objects.create(sku="NOPRICE", name="Narxsiz tovar", unit=dona)
    # cola — so'mda narx; shakar — faqat dollarda (so'mga kurs bilan o'tadi: 1,20 × 12 500)
    catalog_services.set_price(
        actor=owner, product=cola, price_type=retail, currency=uzs, amount=D("10000")
    )
    catalog_services.set_price(
        actor=owner, product=sugar, price_type=retail, currency=usd, amount=D("1.20")
    )
    return {"cola": cola, "sugar": sugar, "noprice": nopr}


@pytest.fixture
def stocked(owner, branch, products):
    """Cola: 10 dona @0,60 + 10 dona @0,70 (FIFO uchun ikki partiya); shakar 5 kg @0,80."""

    def receive(product, qty, cost, doc_id):
        return inventory_services.receive_stock(
            actor=owner,
            branch_id=branch.id,
            product_id=product.id,
            quantity=D(qty),
            unit_cost_base=D(cost),
            movement_type=MovementType.PURCHASE_IN,
            doc=DocRef(type="purchase", id=doc_id, number=f"K-{doc_id}"),
        )

    return {
        "cola1": receive(products["cola"], "10", "0.60", 1),
        "cola2": receive(products["cola"], "10", "0.70", 2),
        "sugar": receive(products["sugar"], "5", "0.80", 3),
    }


def sale_payload(branch, currency, items, payments, **extra):
    return {
        "branch": branch.id,
        "currency": currency.id,
        "items": items,
        "payments": payments,
        **extra,
    }
