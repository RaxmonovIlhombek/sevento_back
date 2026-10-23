from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.catalog import selectors, services
from apps.catalog.models import Category, PriceType, Product, Unit
from apps.currency.models import Currency

pytestmark = pytest.mark.django_db

CATS = "/api/v1/catalog/categories/"
PRODUCTS = "/api/v1/catalog/products/"


@pytest.fixture
def unit(db) -> Unit:
    return Unit.objects.get(code="dona")


@pytest.fixture
def kg(db) -> Unit:
    return Unit.objects.get(code="kg")


@pytest.fixture
def retail(db) -> PriceType:
    return PriceType.objects.get(code="retail")


@pytest.fixture
def wholesale(db) -> PriceType:
    return PriceType.objects.get(code="wholesale")


@pytest.fixture
def usd(db) -> Currency:
    return Currency.objects.get(code="USD")


@pytest.fixture
def uzs(db) -> Currency:
    return Currency.objects.get(code="UZS")


@pytest.fixture
def tree(db):
    root = Category.objects.create(name="Ichimliklar")
    child = Category.objects.create(name="Suv", parent=root)
    grand = Category.objects.create(name="Gazli", parent=child)
    other = Category.objects.create(name="Non")
    return {"root": root, "child": child, "grand": grand, "other": other}


@pytest.fixture
def product(db, unit, tree) -> Product:
    return Product.objects.create(
        sku="P-001", name="Gazli suv 1L", unit=unit, category=tree["grand"]
    )


# --- seed ---


def test_seeded_units_and_price_types(unit, kg, retail, wholesale):
    assert unit.decimal_places == 0 and kg.decimal_places == 3
    assert retail.is_default and not wholesale.is_default
    assert selectors.default_price_type() == retail


# --- kategoriyalar ---


def test_category_tree_and_descendants(owner_client, tree):
    body = owner_client.get(f"{CATS}tree/").json()
    assert [n["name"] for n in body] == ["Ichimliklar", "Non"]
    assert body[0]["children"][0]["name"] == "Suv"
    assert body[0]["children"][0]["children"][0]["name"] == "Gazli"
    assert selectors.descendant_ids(tree["root"].id) == {
        tree["root"].id,
        tree["child"].id,
        tree["grand"].id,
    }


def test_category_create_update_and_cycle(owner_client, tree, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        response = owner_client.post(CATS, {"name": "Sharbat", "parent": tree["root"].id})
    assert response.status_code == 201, response.json()
    assert response.json()["parent_name"] == "Ichimliklar"
    assert AuditLog.objects.filter(event_name="category.created").exists()

    # bir darajada bir xil nom
    response = owner_client.post(CATS, {"name": "sharbat", "parent": tree["root"].id})
    assert response.status_code == 400
    assert response.json()["error"]["details"][0]["field"] == "name"
    # boshqa darajada mumkin
    assert owner_client.post(CATS, {"name": "Sharbat"}).status_code == 201

    # sikl: ildizni o'z avlodi ichiga ko'chirish
    response = owner_client.patch(f"{CATS}{tree['root'].id}/", {"parent": tree["grand"].id})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "category_cycle"
    response = owner_client.patch(f"{CATS}{tree['root'].id}/", {"parent": tree["root"].id})
    assert response.status_code == 400

    # oddiy ko'chirish
    with django_capture_on_commit_callbacks(execute=True):
        response = owner_client.patch(f"{CATS}{tree['grand'].id}/", {"parent": tree["other"].id})
    assert response.status_code == 200
    changes = AuditLog.objects.get(event_name="category.updated").payload["changes"]
    assert changes == {"parent": {"old": tree["child"].id, "new": tree["other"].id}}


def test_category_permissions(seller_client, storekeeper, as_user, tree):
    assert seller_client.get(CATS).status_code == 200
    assert seller_client.post(CATS, {"name": "X"}).status_code == 403
    assert as_user(storekeeper).post(CATS, {"name": "X"}).status_code == 201


# --- birliklar va narx turlari ---


def test_units_and_price_types_api(owner_client, django_capture_on_commit_callbacks):
    response = owner_client.get("/api/v1/catalog/units/")
    assert {u["code"] for u in response.json()} >= {"dona", "kg", "m", "l"}

    with django_capture_on_commit_callbacks(execute=True):
        response = owner_client.post(
            "/api/v1/catalog/units/", {"code": "QOP", "name": "Qop", "decimal_places": 0}
        )
    assert response.status_code == 201 and response.json()["code"] == "qop"
    assert (
        owner_client.post("/api/v1/catalog/units/", {"code": "qop", "name": "X"}).status_code == 400
    )
    assert (
        owner_client.post(
            "/api/v1/catalog/units/", {"code": "x", "name": "X", "decimal_places": 5}
        ).status_code
        == 400
    )

    # faqat bitta default narx turi
    response = owner_client.post(
        "/api/v1/catalog/price-types/", {"code": "vip", "name": "VIP", "is_default": True}
    )
    assert response.status_code == 201
    assert PriceType.objects.filter(is_default=True).count() == 1
    assert PriceType.objects.get(is_default=True).code == "vip"


# --- tovarlar ---


def test_create_product_and_validation(
    owner_client, unit, tree, django_capture_on_commit_callbacks
):
    payload = {
        "sku": " p-100 ",
        "barcode": "4780000000012",
        "name": "Olma",
        "unit": unit.id,
        "category": tree["other"].id,
        "min_quantity": "10",
    }
    with django_capture_on_commit_callbacks(execute=True):
        response = owner_client.post(PRODUCTS, payload)
    assert response.status_code == 201, response.json()
    body = response.json()
    assert body["sku"] == "P-100"
    assert body["unit_code"] == "dona" and body["category_name"] == "Non"
    assert body["prices"] == []
    assert AuditLog.objects.filter(event_name="product.created").exists()

    dup = owner_client.post(PRODUCTS, {**payload, "sku": "P-100"})
    assert dup.json()["error"]["details"][0] == {
        "field": "sku",
        "code": "unique",
        "message": "Bu artikul band",
    }
    dup = owner_client.post(PRODUCTS, {**payload, "sku": "P-101"})
    assert dup.json()["error"]["details"][0]["field"] == "barcode"
    # shtrix-kodsiz tovarlar ko'p bo'lishi mumkin
    assert (
        owner_client.post(PRODUCTS, {**payload, "sku": "P-102", "barcode": ""}).status_code == 201
    )
    assert (
        owner_client.post(PRODUCTS, {**payload, "sku": "P-103", "barcode": ""}).status_code == 201
    )


def test_product_list_filters_and_search(owner_client, unit, tree):
    Product.objects.create(
        sku="A1", name="Gazli suv", unit=unit, category=tree["grand"], barcode="111"
    )
    Product.objects.create(sku="A2", name="Suv oddiy", unit=unit, category=tree["child"])
    Product.objects.create(sku="B1", name="Non", unit=unit, category=tree["other"], is_active=False)

    assert owner_client.get(PRODUCTS).json()["count"] == 3
    # ota kategoriya avlodlarini ham qamrab oladi
    assert owner_client.get(PRODUCTS, {"category": tree["root"].id}).json()["count"] == 2
    assert owner_client.get(PRODUCTS, {"category": tree["grand"].id}).json()["count"] == 1
    assert owner_client.get(PRODUCTS, {"is_active": "false"}).json()["results"][0]["sku"] == "B1"
    assert owner_client.get(PRODUCTS, {"search": "suv"}).json()["count"] == 2
    assert owner_client.get(PRODUCTS, {"search": "111"}).json()["results"][0]["sku"] == "A1"
    assert owner_client.get(PRODUCTS, {"search": "a2"}).json()["results"][0]["sku"] == "A2"


def test_update_product_tracks_changes(
    owner_client, product, kg, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        response = owner_client.patch(
            f"{PRODUCTS}{product.id}/", {"name": "Gazli suv 1.5L", "unit": kg.id}
        )
    assert response.status_code == 200
    changes = AuditLog.objects.get(event_name="product.updated").payload["changes"]
    assert changes["name"]["new"] == "Gazli suv 1.5L"
    assert changes["unit"] == {"old": product.unit_id, "new": kg.id}


def test_product_permissions(seller_client, storekeeper, accountant, as_user, product, retail, uzs):
    assert seller_client.get(PRODUCTS).status_code == 200
    assert seller_client.post(PRODUCTS, {"sku": "X"}).status_code == 403
    assert as_user(storekeeper).patch(f"{PRODUCTS}{product.id}/", {"name": "Y"}).status_code == 200
    price = {"price_type": retail.id, "currency": uzs.id, "amount": "12000"}
    assert as_user(storekeeper).post(f"{PRODUCTS}{product.id}/set-price/", price).status_code == 403
    assert as_user(accountant).post(f"{PRODUCTS}{product.id}/set-price/", price).status_code == 201


def test_effective_min_quantity(product):
    assert selectors.effective_min_quantity(product) == Decimal("5")  # sozlama default
    product.min_quantity = Decimal("2.5")
    assert selectors.effective_min_quantity(product) == Decimal("2.5")


# --- narxlar ---


def test_price_history_and_current_resolution(
    owner,
    owner_client,
    product,
    retail,
    wholesale,
    usd,
    uzs,
    branch,
    branch2,
    django_capture_on_commit_callbacks,
):
    url = f"{PRODUCTS}{product.id}/set-price/"
    with django_capture_on_commit_callbacks(execute=True):
        r1 = owner_client.post(
            url, {"price_type": retail.id, "currency": uzs.id, "amount": "12000"}
        )
        r2 = owner_client.post(
            url, {"price_type": retail.id, "currency": uzs.id, "amount": "12500"}
        )
        r3 = owner_client.post(
            url,
            {"price_type": retail.id, "currency": uzs.id, "amount": "11900", "branch": branch.id},
        )
        r4 = owner_client.post(
            url, {"price_type": wholesale.id, "currency": usd.id, "amount": "0.9"}
        )
        future = (timezone.now() + timedelta(days=1)).isoformat()
        r5 = owner_client.post(
            url,
            {"price_type": retail.id, "currency": uzs.id, "amount": "99999", "valid_from": future},
        )
    for r in (r1, r2, r3, r4, r5):
        assert r.status_code == 201, r.json()

    # hodisa: eski va yangi narx
    events = AuditLog.objects.filter(event_name="product.price_changed").order_by("id")
    assert events[1].payload["old_amount"] == "12000.0000"
    assert events[1].payload["new_amount"] == "12500.0000"

    # umumiy joriy narx: 12500 (kelajakdagi 99999 emas)
    body = owner_client.get(f"{PRODUCTS}{product.id}/").json()
    assert {(p["price_type"], p["currency"]): p["amount"] for p in body["prices"]} == {
        ("retail", "UZS"): "12500.0000",
        ("wholesale", "USD"): "0.9000",
    }
    # nuqtaga xos narx ustun
    body = owner_client.get(f"{PRODUCTS}{product.id}/", {"branch": branch.id}).json()
    retail_uzs = next(p for p in body["prices"] if p["price_type"] == "retail")
    assert retail_uzs["amount"] == "11900.0000" and retail_uzs["branch"] == branch.id
    # boshqa nuqtada umumiy
    body = owner_client.get(f"{PRODUCTS}{product.id}/", {"branch": branch2.id}).json()
    assert next(p for p in body["prices"] if p["price_type"] == "retail")["amount"] == "12500.0000"

    # tarix
    history = owner_client.get(f"{PRODUCTS}{product.id}/prices/").json()
    assert len(history) == 5
    assert history[0]["amount"] == "99999.0000"  # eng so'nggi valid_from birinchi
    assert history[1]["branch_name"] is None or history[1]["branch_name"] == branch.name

    # ro'yxatda ham narxlar (bitta so'rov bilan)
    body = owner_client.get(PRODUCTS, {"branch": branch.id}).json()
    assert body["results"][0]["prices"][0]["amount"] == "11900.0000"


def test_set_price_branch_access(seller, as_user, accountant, product, retail, uzs, branch2):
    """Sotuvchi narx qo'ya olmaydi; buxgalter begona nuqta uchun ham qo'ya oladi (view_all)."""
    client = as_user(accountant)
    response = client.post(
        f"{PRODUCTS}{product.id}/set-price/",
        {"price_type": retail.id, "currency": uzs.id, "amount": "100", "branch": branch2.id},
    )
    assert response.status_code == 201
    assert response.json()["branch_name"] == branch2.name


def test_set_price_validation(owner_client, product, retail, uzs):
    response = owner_client.post(
        f"{PRODUCTS}{product.id}/set-price/",
        {"price_type": retail.id, "currency": uzs.id, "amount": "-1"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["details"][0]["field"] == "amount"


def test_service_set_price_and_current_price(owner, product, retail, uzs, branch):
    services.set_price(
        actor=owner, product=product, price_type=retail, currency=uzs, amount=Decimal("10")
    )
    services.set_price(
        actor=owner,
        product=product,
        price_type=retail,
        currency=uzs,
        amount=Decimal("12"),
        branch=branch,
    )
    assert selectors.current_price(product, retail, "UZS").amount == Decimal("10")
    assert selectors.current_price(product, retail, "UZS", branch.id).amount == Decimal("12")
    assert selectors.current_price(product, retail, "USD") is None
