import json
from datetime import date, timedelta
from decimal import Decimal

import httpx
import pytest
from django.core.cache import cache

from apps.audit.models import AuditLog
from apps.currency import selectors, services
from apps.currency.models import Currency, ExchangeRate
from apps.currency.providers import CbuRateProvider, ProviderError
from apps.currency.selectors import RateUnavailable
from apps.currency.tasks import fetch_rates as fetch_rates_task
from core.models import OutboxEvent

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def usd(db) -> Currency:
    return Currency.objects.get(code="USD")


@pytest.fixture
def uzs(db) -> Currency:
    return Currency.objects.get(code="UZS")


# --- seed va valyutalar ---


def test_seeded_currencies(usd, uzs):
    assert usd.decimal_places == 2 and uzs.decimal_places == 0
    assert selectors.base_currency().code == "USD"


def test_create_currency_api(owner_client, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        response = owner_client.post(
            "/api/v1/currencies/", {"code": "eur", "name": "Yevro", "symbol": "€"}
        )
    assert response.status_code == 201, response.json()
    assert response.json()["code"] == "EUR"
    assert AuditLog.objects.filter(event_name="currency.created").exists()

    response = owner_client.post("/api/v1/currencies/", {"code": "EUR", "name": "X"})
    assert response.json()["error"]["details"][0]["code"] == "unique"
    response = owner_client.post("/api/v1/currencies/", {"code": "EURO", "name": "X"})
    assert response.json()["error"]["details"][0]["field"] == "code"


def test_currency_list_for_everyone_write_for_owner(seller_client, usd):
    response = seller_client.get("/api/v1/currencies/")
    assert response.status_code == 200
    assert [(c["code"], c["is_base"]) for c in response.json()] == [("USD", True), ("UZS", False)]
    assert seller_client.patch(f"/api/v1/currencies/{usd.id}/", {"name": "x"}).status_code == 403


def test_cannot_deactivate_base_or_quote(owner_client, usd, uzs):
    for currency in (usd, uzs):
        response = owner_client.patch(f"/api/v1/currencies/{currency.id}/", {"is_active": False})
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "currency_required"
    response = owner_client.patch(f"/api/v1/currencies/{usd.id}/", {"code": "USX"})
    assert response.json()["error"]["code"] == "currency_code_locked"


# --- kurslar ---


def test_set_manual_rate_and_latest(accountant, as_user, usd, django_capture_on_commit_callbacks):
    client = as_user(accountant)
    with django_capture_on_commit_callbacks(execute=True):
        response = client.post("/api/v1/currency-rates/", {"currency": usd.id, "rate": "12650.5"})
    assert response.status_code == 201, response.json()
    body = response.json()
    assert body["currency_code"] == "USD" and body["source"] == "manual"
    assert Decimal(body["rate"]) == Decimal("12650.5")
    assert body["created_by_name"] == accountant.full_name

    event = OutboxEvent.objects.get(name="currency.rate_updated")
    assert event.payload["rates"] == [
        {"currency": "USD", "rate": "12650.500000", "date": date.today().isoformat()}
    ]
    assert AuditLog.objects.filter(event_name="currency.rate_updated").exists()

    latest = client.get("/api/v1/currency-rates/latest/").json()
    assert latest == [
        {
            "currency": usd.id,
            "code": "USD",
            "name": "AQSH dollari",
            "symbol": "$",
            "decimal_places": 2,
            "rate": "12650.500000",
            "date": date.today().isoformat(),
            "source": "manual",
        }
    ]


def test_manual_rate_replaces_same_day(accountant, usd):
    services.set_rate(actor=accountant, currency=usd, rate=Decimal("12600"))
    services.set_rate(actor=accountant, currency=usd, rate=Decimal("12700"))
    assert ExchangeRate.objects.count() == 1
    assert selectors.rate_value("USD") == Decimal("12700")


def test_rate_validation(owner_client, usd, uzs):
    response = owner_client.post("/api/v1/currency-rates/", {"currency": usd.id, "rate": "-1"})
    assert response.status_code == 400
    response = owner_client.post("/api/v1/currency-rates/", {"currency": uzs.id, "rate": "1"})
    assert response.json()["error"]["code"] == "quote_currency"


def test_seller_cannot_set_rate(seller_client, usd):
    assert (
        seller_client.post("/api/v1/currency-rates/", {"currency": usd.id, "rate": "1"}).status_code
        == 403
    )
    assert seller_client.get("/api/v1/currency-rates/latest/").status_code == 200


def test_latest_rate_by_date_and_history_filters(owner, owner_client, usd):
    today = date.today()
    services.set_rate(
        actor=owner, currency=usd, rate=Decimal("12000"), day=today - timedelta(days=2)
    )
    services.set_rate(
        actor=owner, currency=usd, rate=Decimal("12500"), day=today - timedelta(days=1)
    )
    services.set_rate(
        actor=owner, currency=usd, rate=Decimal("13000"), day=today + timedelta(days=1)
    )

    assert selectors.rate_value("USD") == Decimal("12500")  # kelajakdagi kurs hisobga olinmaydi
    assert selectors.rate_value("USD", on=today - timedelta(days=2)) == Decimal("12000")
    with pytest.raises(RateUnavailable):
        selectors.rate_value("USD", on=today - timedelta(days=10))

    body = owner_client.get("/api/v1/currency-rates/", {"code": "usd"}).json()
    assert body["count"] == 3
    assert [r["rate"] for r in body["results"]][0] == "13000.000000"
    assert (
        owner_client.get("/api/v1/currency-rates/", {"date_from": today.isoformat()}).json()[
            "count"
        ]
        == 1
    )


# --- konvertatsiya ---


def test_convert(owner, usd):
    services.set_rate(actor=owner, currency=usd, rate=Decimal("12500"))
    assert services.convert(Decimal("2"), "USD", "UZS") == Decimal("25000.0000")
    assert services.convert(Decimal("25000"), "UZS", "USD") == Decimal("2.0000")
    assert services.convert(Decimal("7"), "USD", "USD") == Decimal("7")
    assert services.to_base(Decimal("12500"), "UZS") == Decimal("1.0000")
    assert services.convert(Decimal("1"), "UZS", "UZS") == Decimal("1")
    assert services.convert(Decimal("1"), "uzs", "USD") == Decimal("0.0001")


def test_rate_to_base(owner, usd):
    services.set_rate(actor=owner, currency=usd, rate=Decimal("12500"))
    assert selectors.rate_to_base("USD") == Decimal(1)  # asosiy valyuta
    assert selectors.rate_to_base("uzs") == Decimal("0.000080000000")
    assert Decimal("25000") * selectors.rate_to_base("UZS") == Decimal("2.000000000000")


def test_convert_without_rate_raises(usd):
    with pytest.raises(RateUnavailable):
        services.convert(Decimal("1"), "USD", "UZS")


# --- CBU adapteri ---

CBU_PAYLOAD = [
    {
        "id": 69,
        "Code": "840",
        "Ccy": "USD",
        "Nominal": "1",
        "Rate": "12650.45",
        "Date": "22.10.2026",
    },
    {
        "id": 21,
        "Code": "978",
        "Ccy": "EUR",
        "Nominal": "1",
        "Rate": "13700.10",
        "Date": "22.10.2026",
    },
    {
        "id": 7,
        "Code": "392",
        "Ccy": "JPY",
        "Nominal": "100",
        "Rate": "8500.00",
        "Date": "22.10.2026",
    },
]


def _transport(handler):
    return httpx.MockTransport(handler)


def test_cbu_provider_parses_nominal_and_date():
    provider = CbuRateProvider(
        transport=_transport(lambda r: httpx.Response(200, json=CBU_PAYLOAD))
    )
    quotes = provider.fetch_rates(["usd", "JPY"])
    assert {q.code: (q.rate, q.date) for q in quotes} == {
        "USD": (Decimal("12650.45"), date(2026, 10, 22)),
        "JPY": (Decimal("85.00"), date(2026, 10, 22)),
    }


def test_cbu_provider_errors():
    with pytest.raises(ProviderError):
        CbuRateProvider(transport=_transport(lambda r: httpx.Response(500))).fetch_rates(["USD"])
    with pytest.raises(ProviderError):
        CbuRateProvider(
            transport=_transport(lambda r: httpx.Response(200, text="html"))
        ).fetch_rates(["USD"])
    with pytest.raises(ProviderError):
        CbuRateProvider(
            transport=_transport(lambda r: httpx.Response(200, json=[{"Ccy": "USD", "Rate": "x"}]))
        ).fetch_rates(["USD"])


def test_fetch_rates_service_and_task(monkeypatch, usd, django_capture_on_commit_callbacks):
    def fake_provider(key, **kwargs):
        return CbuRateProvider(
            transport=_transport(lambda r: httpx.Response(200, json=CBU_PAYLOAD))
        )

    monkeypatch.setattr(services, "get_provider", fake_provider)
    with django_capture_on_commit_callbacks(execute=True):
        rows = services.fetch_rates()
    assert [(r.currency.code, r.source) for r in rows] == [("USD", "cbu")]  # EUR jadvalda yo'q
    assert selectors.rate_value("USD", on=date(2026, 10, 22)) == Decimal("12650.45")
    event = OutboxEvent.objects.get(name="currency.rate_updated")
    assert event.payload["source"] == "cbu"
    assert event.actor_id is None

    assert fetch_rates_task() == 1  # CELERY_TASK_ALWAYS_EAGER


def test_fetch_endpoint_and_provider_error(monkeypatch, owner_client, usd):
    def failing(key, **kwargs):
        return CbuRateProvider(transport=_transport(lambda r: httpx.Response(503)))

    monkeypatch.setattr(services, "get_provider", failing)
    response = owner_client.post("/api/v1/currency-rates/fetch/")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "rate_provider_unavailable"

    def ok(key, **kwargs):
        return CbuRateProvider(
            transport=_transport(lambda r: httpx.Response(200, json=CBU_PAYLOAD))
        )

    monkeypatch.setattr(services, "get_provider", ok)
    response = owner_client.post("/api/v1/currency-rates/fetch/")
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "cbu"
    assert [r["currency_code"] for r in body["updated"]] == ["USD"]


def test_manual_provider_setting_fetches_nothing(
    owner_client, usd, django_capture_on_commit_callbacks
):
    from core import settings_service

    with django_capture_on_commit_callbacks(execute=True):
        settings_service.set(key="currency.rate_provider", value="manual", actor=None)
    assert services.fetch_rates() == []


def test_cbu_url_setting(settings):
    settings.CURRENCY_CBU_URL = "https://example.test/rates.json"
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        return httpx.Response(200, content=json.dumps([]))

    CbuRateProvider(transport=_transport(handler)).fetch_rates(["USD"])
    assert seen["url"] == "https://example.test/rates.json"


def test_update_currency_records_changes_once(
    owner_client, usd, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        response = owner_client.patch(
            f"/api/v1/currencies/{usd.id}/", {"name": "AQSh dollari", "symbol": "$"}
        )
    assert response.status_code == 200, response.json()
    event = OutboxEvent.objects.get(name="currency.updated")
    assert event.payload["code"] == "USD"
    assert event.payload["changes"]["name"]["new"] == "AQSh dollari"
    assert "decimal_places" not in event.payload["changes"]

    # o'zgarishsiz saqlash hodisa chiqarmaydi
    with django_capture_on_commit_callbacks(execute=True):
        owner_client.patch(f"/api/v1/currencies/{usd.id}/", {"name": "AQSh dollari"})
    assert OutboxEvent.objects.filter(name="currency.updated").count() == 1


def test_fetch_rates_without_foreign_currencies_does_nothing(monkeypatch, usd):
    Currency.objects.exclude(code="UZS").update(is_active=False)

    class NoCall:
        def fetch_rates(self, codes):
            pytest.fail("valyuta yo'q — provayderga murojaat qilinmasin")

    monkeypatch.setattr(services, "get_provider", lambda key, **kw: NoCall())
    assert services.fetch_rates() == []
