"""Ombor hujjatlari testlari uchun: ikkinchi nuqta omborchisi, tovarlar, qoldiq kiritish."""

from decimal import Decimal

import pytest
from django.db import transaction
from django.db.models import Sum

from apps.accounts.models import User, UserBranch
from apps.catalog.models import Product, Unit
from apps.inventory import services
from apps.inventory.models import Batch, StockLevel
from apps.inventory.types import DocRef, MovementType

D = Decimal


@pytest.fixture
def storekeeper2(roles, branch2) -> User:
    user = User.objects.create_user(
        username="omborchi2",
        password="parol12345",
        full_name="Omborchi 2",
        role=roles["storekeeper"],
    )
    UserBranch.objects.create(user=user, branch=branch2, is_default=True)
    return user


@pytest.fixture
def sk_client(storekeeper, as_user):
    return as_user(storekeeper)


@pytest.fixture
def sk2_client(storekeeper2, as_user):
    return as_user(storekeeper2)


@pytest.fixture
def goods(db) -> dict[str, Product]:
    dona = Unit.objects.get(code="dona")
    kg = Unit.objects.get(code="kg")
    return {
        "cola": Product.objects.create(sku="C1", name="Coca-Cola 1L", unit=dona),
        "fanta": Product.objects.create(sku="F1", name="Fanta 1L", unit=dona),
        "sugar": Product.objects.create(sku="S1", name="Shakar", unit=kg),
    }


@pytest.fixture
def stock_in(owner):
    """stock_in(branch, product, qty, cost) — kirim partiyasi (har chaqiruv yangi hujjat)."""
    counter = {"n": 0}

    def receive(branch, product, qty, cost):
        counter["n"] += 1
        with transaction.atomic():
            return services.receive_stock(
                actor=owner,
                branch_id=branch.id,
                product_id=product.id,
                quantity=D(qty),
                unit_cost_base=D(cost),
                movement_type=MovementType.PURCHASE_IN,
                doc=DocRef(type="purchase", id=counter["n"], number=f"K-{counter['n']}", line_id=1),
            )

    return receive


def qty(branch, product) -> Decimal:
    level = StockLevel.objects.filter(branch=branch, product=product).first()
    return level.quantity if level else D(0)


def assert_invariant(branch, product):
    """StockLevel.quantity == SUM(Batch.quantity_remaining)."""
    remaining = Batch.objects.filter(branch=branch, product=product).aggregate(
        s=Sum("quantity_remaining")
    )["s"] or D(0)
    assert qty(branch, product) == remaining
