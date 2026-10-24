"""seed_demo: servislar orqali to'liq oqim (kirim → ko'chirish → savdo → nasiya), idempotent."""

from decimal import Decimal as D
from io import StringIO

import pytest
from django.core.management import call_command

from apps.accounts.models import User
from apps.branches.models import Branch
from apps.inventory.models import StockLevel
from apps.payments.models import Debt
from apps.sales.models import Sale

pytestmark = pytest.mark.django_db


def _run(**kwargs) -> str:
    out = StringIO()
    call_command("seed_demo", stdout=out, **kwargs)
    return out.getvalue()


def test_requires_owner():
    with pytest.raises(Exception, match="bootstrap"):
        _run(password="Demo-parol-1")


def test_seed_creates_consistent_data_and_is_idempotent(owner):
    owner.is_superuser = True
    owner.save()
    output = _run(password="Demo-parol-1")
    assert "Demo ma'lumotlar yaratildi" in output and "Demo-parol-1" not in output

    assert set(Branch.objects.filter(code__startswith="DEMO").values_list("code", flat=True)) == {
        "DEMO1",
        "DEMO2",
        "DEMOW",
    }
    seller = User.objects.get(username="demo_sotuvchi1")
    assert seller.check_password("Demo-parol-1") and seller.role.code == "seller"
    assert Sale.objects.count() == 6
    debt = Debt.objects.get()
    assert debt.amount - debt.paid_amount == D("50000")  # 150 000 qarz − 100 000 to'lov
    # ko'chirishdan keyin ombor: 120 − 36 − 24 = 60 dona Coca-Cola
    warehouse = StockLevel.objects.get(branch__code="DEMOW", product__sku="DM-001")
    assert warehouse.quantity == D("60")

    assert "allaqachon bor" in _run(password="Demo-parol-1")
    assert Sale.objects.count() == 6


def test_generated_password_is_printed(owner, monkeypatch):
    monkeypatch.delenv("DEMO_PASSWORD", raising=False)
    owner.is_superuser = True
    owner.save()
    output = _run()
    password = output.strip().rsplit("parol: ", 1)[1]
    assert len(password) >= 12
    assert User.objects.get(username="demo_omborchi").check_password(password)


def test_conflict_with_existing_user_writes_nothing(owner, roles):
    owner.is_superuser = True
    owner.save()
    User.objects.create_user(username="demo_omborchi", password="x", role=roles["storekeeper"])
    with pytest.raises(Exception, match="demo_omborchi"):
        _run(password="Demo-parol-1")
    assert not Branch.objects.filter(code__startswith="DEMO").exists()
