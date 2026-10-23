"""Kirim: qoralama, tannarx (xarajat taqsimoti, valyuta), qabul qilish, bekor qilish, ruxsatlar."""

from decimal import Decimal

import pytest
from django.db import transaction

from apps.audit.models import AuditLog
from apps.catalog.models import Product, Unit
from apps.currency import services as currency_services
from apps.currency.models import Currency
from apps.inventory import services as inventory_services
from apps.inventory.models import Batch, StockLevel, StockMovement
from apps.inventory.types import DocRef, MovementType
from apps.purchasing.models import ExpenseType, Purchase, Supplier

pytestmark = pytest.mark.django_db

D = Decimal
URL = "/api/v1/purchasing/purchases/"


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
def supplier(db):
    return Supplier.objects.create(name="Coca-Cola Ichimligi")


@pytest.fixture
def products(db):
    dona = Unit.objects.get(code="dona")
    kg = Unit.objects.get(code="kg")
    return {
        "cola": Product.objects.create(sku="COLA", name="Cola 1L", unit=dona),
        "sugar": Product.objects.create(sku="SUGAR", name="Shakar", unit=kg),
    }


@pytest.fixture
def transport(db):
    return ExpenseType.objects.get(code="transport")


@pytest.fixture
def loading(db):
    return ExpenseType.objects.get(code="loading")


def payload(branch, supplier, currency, products, items=None, expenses=None, **extra):
    return {
        "branch": branch.id,
        "supplier": supplier.id,
        "currency": currency.id,
        "invoice_number": "INV-77",
        "items": items
        if items is not None
        else [
            {"product": products["cola"].id, "quantity": "100", "unit_price": "0.80"},
            {"product": products["sugar"].id, "quantity": "50", "unit_price": "0.40"},
        ],
        "expenses": expenses or [],
        **extra,
    }


def test_seeded_expense_types(transport, loading):
    assert transport.default_allocation == "by_value"
    assert loading.default_allocation == "by_quantity"


def test_create_draft_with_number(
    owner_client, branch, supplier, usd, products, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        response = owner_client.post(URL, payload(branch, supplier, usd, products), format="json")
    assert response.status_code == 201, response.json()
    body = response.json()
    assert body["number"].startswith("K-TSH1-") and body["number"].endswith("-000001")
    assert body["status"] == "draft"
    assert body["subtotal"] == "100.0000"  # 100*0.8 + 50*0.4
    assert [i["line_total"] for i in body["items"]] == ["80.0000", "20.0000"]
    assert body["can_cancel"] is True
    assert body["base_currency"] == "USD"
    assert not StockLevel.objects.exists()  # qoralama qoldiqqa ta'sir qilmaydi
    assert AuditLog.objects.filter(event_name="purchase.created").exists()


def test_unit_precision_and_inactive_product(owner_client, branch, supplier, usd, products):
    items = [{"product": products["cola"].id, "quantity": "1.5", "unit_price": "1"}]
    response = owner_client.post(
        URL, payload(branch, supplier, usd, products, items=items), format="json"
    )
    assert response.status_code == 400
    assert response.json()["error"]["details"][0] == {
        "field": "items.0.quantity",
        "code": "unit_precision",
        "message": "«Dona» uchun ko'pi bilan 0 xona kasr",
    }
    # kg — 3 xonagacha mumkin
    items = [{"product": products["sugar"].id, "quantity": "1.255", "unit_price": "1"}]
    assert (
        owner_client.post(
            URL, payload(branch, supplier, usd, products, items=items), format="json"
        ).status_code
        == 201
    )

    Product.objects.filter(pk=products["cola"].pk).update(is_active=False)
    items = [{"product": products["cola"].id, "quantity": "1", "unit_price": "1"}]
    response = owner_client.post(
        URL, payload(branch, supplier, usd, products, items=items), format="json"
    )
    assert response.json()["error"]["details"][0]["code"] == "product_inactive"


def test_receive_usd_purchase_with_uzs_expenses(
    owner_client,
    owner,
    branch,
    supplier,
    usd,
    uzs,
    products,
    transport,
    loading,
    rate,
    django_capture_on_commit_callbacks,
):
    """USD kirim + transport 250 000 so'm (qiymat bo'yicha) + yuklash 5 USD (miqdor bo'yicha)."""
    expenses = [
        {"expense_type": transport.id, "currency": uzs.id, "amount": "250000"},  # = 20 USD
        {"expense_type": loading.id, "currency": usd.id, "amount": "5"},
    ]
    created = owner_client.post(
        URL, payload(branch, supplier, usd, products, expenses=expenses), format="json"
    ).json()
    assert [e["allocation_method"] for e in created["expenses"]] == ["by_value", "by_quantity"]

    preview = owner_client.get(f"{URL}{created['id']}/preview/").json()
    assert preview["expenses_total_base"] == "25.0000"
    assert preview["total_base"] == "125.0000"

    with django_capture_on_commit_callbacks(execute=True):
        response = owner_client.post(f"{URL}{created['id']}/receive/")
    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["status"] == "received"
    assert body["rate_to_base"] == "1.000000000000"
    assert body["expenses_total_base"] == "25.0000"
    assert body["total_base"] == "125.0000"
    assert [e["amount_base"] for e in body["expenses"]] == ["20.0000", "5.0000"]

    cola, sugar = body["items"]
    # transport 20 USD qiymat bo'yicha: 80/100 → 16, 20/100 → 4
    # yuklash 5 USD miqdor bo'yicha: 100/150 → 3.3334, 50/150 → 1.6666 (qoldiq kattaroqqa)
    assert cola["allocated_expense_base"] == "19.3334"
    assert sugar["allocated_expense_base"] == "5.6666"
    assert cola["landed_unit_cost_base"] == "0.993334"  # (80 + 19.3334) / 100
    assert sugar["landed_unit_cost_base"] == "0.513332"  # (20 + 5.6666) / 50

    # partiyalar va qoldiq
    batches = Batch.objects.filter(source_type="purchase", source_id=created["id"]).order_by("id")
    assert [(b.product_id, b.quantity_initial, b.unit_cost_base) for b in batches] == [
        (products["cola"].id, D("100"), D("0.993334")),
        (products["sugar"].id, D("50"), D("0.513332")),
    ]
    assert StockLevel.objects.get(branch=branch, product=products["cola"]).quantity == D("100")
    assert StockMovement.objects.filter(document_type="purchase", type="purchase_in").count() == 2
    log = AuditLog.objects.get(event_name="purchase.received")
    assert log.payload["total_base"] == "125.0000"
    assert body["can_cancel"] is True


def test_receive_uzs_purchase_converts_to_base(owner_client, branch, supplier, uzs, products, rate):
    items = [{"product": products["cola"].id, "quantity": "10", "unit_price": "12500"}]
    created = owner_client.post(
        URL, payload(branch, supplier, uzs, products, items=items), format="json"
    ).json()
    body = owner_client.post(f"{URL}{created['id']}/receive/").json()
    assert body["subtotal"] == "125000.0000"
    assert body["subtotal_base"] == "10.0000"
    assert body["items"][0]["landed_unit_cost_base"] == "1.000000"


def test_receive_without_rate_is_409(owner_client, branch, supplier, uzs, products):
    created = owner_client.post(URL, payload(branch, supplier, uzs, products), format="json").json()
    response = owner_client.post(f"{URL}{created['id']}/receive/")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "rate_unavailable"
    assert Purchase.objects.get(pk=created["id"]).status == "draft"
    assert not StockLevel.objects.exists()


def test_status_transitions(owner_client, branch, supplier, usd, products):
    created = owner_client.post(URL, payload(branch, supplier, usd, products), format="json").json()
    url = f"{URL}{created['id']}/"
    owner_client.post(f"{url}receive/")

    response = owner_client.post(f"{url}receive/")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_status_transition"

    response = owner_client.patch(url, {"note": "x"}, format="json")
    assert response.status_code == 409  # qabul qilingan tahrirlanmaydi

    empty = owner_client.post(
        URL, payload(branch, supplier, usd, products, items=[]), format="json"
    ).json()
    response = owner_client.post(f"{URL}{empty['id']}/receive/")
    assert response.json()["error"]["code"] == "purchase_empty"


def test_update_draft_replaces_lines(owner_client, branch, supplier, usd, products, transport):
    created = owner_client.post(URL, payload(branch, supplier, usd, products), format="json").json()
    url = f"{URL}{created['id']}/"
    response = owner_client.patch(
        url,
        {
            "items": [{"product": products["sugar"].id, "quantity": "2.5", "unit_price": "1.2"}],
            "invoice_number": "INV-78",
        },
        format="json",
    )
    assert response.status_code == 200, response.json()
    body = response.json()
    assert len(body["items"]) == 1 and body["subtotal"] == "3.0000"
    assert body["invoice_number"] == "INV-78"
    assert body["expenses"] == []  # expenses berilmadi — tegilmaydi

    response = owner_client.patch(
        url,
        {"expenses": [{"expense_type": transport.id, "currency": usd.id, "amount": "1"}]},
        format="json",
    )
    assert len(response.json()["expenses"]) == 1
    assert len(response.json()["items"]) == 1  # items berilmadi — tegilmaydi


def test_cancel_received_untouched_and_consumed(
    owner_client, owner, branch, supplier, usd, products
):
    created = owner_client.post(URL, payload(branch, supplier, usd, products), format="json").json()
    url = f"{URL}{created['id']}/"
    owner_client.post(f"{url}receive/")

    # partiyadan 1 dona sotildi → bekor qilib bo'lmaydi
    with transaction.atomic():
        inventory_services.issue_stock(
            actor=owner,
            branch_id=branch.id,
            product_id=products["cola"].id,
            quantity=D("1"),
            movement_type=MovementType.SALE_OUT,
            doc=DocRef(type="sale", id=1),
        )
    assert owner_client.get(url).json()["can_cancel"] is False
    response = owner_client.post(f"{url}cancel/", {"reason": "Xato"}, format="json")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "batch_consumed"

    # boshqa kirim — tegilmagan → bekor qilinadi, qoldiq qaytadi
    created2 = owner_client.post(
        URL, payload(branch, supplier, usd, products), format="json"
    ).json()
    url2 = f"{URL}{created2['id']}/"
    owner_client.post(f"{url2}receive/")
    assert StockLevel.objects.get(branch=branch, product=products["sugar"]).quantity == D("100")
    response = owner_client.post(
        f"{url2}cancel/", {"reason": "Noto'g'ri yetkazib beruvchi"}, format="json"
    )
    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["status"] == "cancelled" and body["cancel_reason"] == "Noto'g'ri yetkazib beruvchi"
    assert StockLevel.objects.get(branch=branch, product=products["sugar"]).quantity == D("50")
    assert (
        StockMovement.objects.filter(document_id=created2["id"], type="purchase_cancel").count()
        == 2
    )

    # bekor qilinganini qayta bekor qilib bo'lmaydi
    assert owner_client.post(f"{url2}cancel/", {"reason": "x"}, format="json").status_code == 409


def test_cancel_draft(owner_client, branch, supplier, usd, products):
    created = owner_client.post(URL, payload(branch, supplier, usd, products), format="json").json()
    response = owner_client.post(
        f"{URL}{created['id']}/cancel/", {"reason": "Kerak emas"}, format="json"
    )
    assert response.json()["status"] == "cancelled"
    assert not StockMovement.objects.exists()


def test_receive_is_idempotent(owner_client, branch, supplier, usd, products):
    created = owner_client.post(URL, payload(branch, supplier, usd, products), format="json").json()
    url = f"{URL}{created['id']}/receive/"
    first = owner_client.post(url, HTTP_IDEMPOTENCY_KEY="k-1")
    second = owner_client.post(url, HTTP_IDEMPOTENCY_KEY="k-1")
    assert first.status_code == second.status_code == 200
    assert second.json()["status"] == "received"
    assert StockMovement.objects.filter(type="purchase_in").count() == 2  # ikki marta emas


def test_permissions_and_branch_scope(
    owner_client,
    seller_client,
    accountant,
    storekeeper,
    as_user,
    branch,
    branch2,
    supplier,
    usd,
    products,
):
    keeper = as_user(storekeeper)
    # sotuvchi kirimni umuman ko'rmaydi
    assert seller_client.get(URL).status_code == 403
    # buxgalter ko'radi, lekin yarata olmaydi
    assert as_user(accountant).get(URL).status_code == 200
    assert (
        as_user(accountant)
        .post(URL, payload(branch, supplier, usd, products), format="json")
        .status_code
        == 403
    )
    # omborchi o'z nuqtasiga — mumkin, begona nuqtaga — 403
    assert (
        keeper.post(URL, payload(branch, supplier, usd, products), format="json").status_code == 201
    )
    response = keeper.post(URL, payload(branch2, supplier, usd, products), format="json")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "branch_forbidden"
    # rahbar yaratgan begona nuqta kirimi omborchiga ko'rinmaydi
    other = owner_client.post(URL, payload(branch2, supplier, usd, products), format="json").json()
    assert keeper.get(f"{URL}{other['id']}/").status_code == 404
    assert keeper.get(URL).json()["count"] == 1


def test_list_filters(owner_client, branch, supplier, usd, products):
    a = owner_client.post(URL, payload(branch, supplier, usd, products), format="json").json()
    owner_client.post(
        URL, payload(branch, supplier, usd, products, invoice_number="ZZ-1"), format="json"
    )
    owner_client.post(f"{URL}{a['id']}/receive/")
    assert owner_client.get(URL, {"status": "received"}).json()["count"] == 1
    assert owner_client.get(URL, {"status": ["draft", "received"]}).json()["count"] == 2
    assert owner_client.get(URL, {"search": "ZZ-1"}).json()["count"] == 1
    assert owner_client.get(URL, {"search": "coca"}).json()["count"] == 2
    row = owner_client.get(URL).json()["results"][0]
    assert row["items_count"] == 2 and row["supplier_name"] == "Coca-Cola Ichimligi"


def test_suppliers_and_expense_types_api(
    owner_client, seller_client, storekeeper, as_user, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        response = as_user(storekeeper).post(
            "/api/v1/purchasing/suppliers/",
            {"name": "Nestle", "phone": "+998901112233", "tin": "301234567"},
        )
    assert response.status_code == 201, response.json()
    assert response.json()["purchases_count"] == 0
    assert AuditLog.objects.get(event_name="supplier.saved").payload["created"] is True
    assert seller_client.get("/api/v1/purchasing/suppliers/").status_code == 403
    assert (
        owner_client.get("/api/v1/purchasing/suppliers/", {"search": "nest"}).json()["count"] == 1
    )

    response = owner_client.post(
        "/api/v1/purchasing/expense-types/", {"code": "Ins", "name": "Sug'urta"}
    )
    assert response.status_code == 201 and response.json()["code"] == "ins"
    assert (
        owner_client.post(
            "/api/v1/purchasing/expense-types/", {"code": "ins", "name": "X"}
        ).status_code
        == 400
    )
    codes = {e["code"] for e in owner_client.get("/api/v1/purchasing/expense-types/").json()}
    assert codes >= {"transport", "customs", "loading", "ins"}
