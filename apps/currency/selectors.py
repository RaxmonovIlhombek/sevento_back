from datetime import date
from decimal import Decimal

from django.db.models import QuerySet
from django.utils import timezone

from core import settings_service
from core.exceptions import BusinessRuleError

from .models import QUOTE_CODE, Currency, ExchangeRate


class RateUnavailable(BusinessRuleError):
    code = "rate_unavailable"
    message = "Valyuta kursi kiritilmagan"


def all_currencies() -> QuerySet[Currency]:
    return Currency.objects.all()


def active_currencies() -> QuerySet[Currency]:
    return Currency.objects.filter(is_active=True)


def get_currency(code: str) -> Currency | None:
    return Currency.objects.filter(code=code.upper()).first()


def base_currency_code() -> str:
    return str(settings_service.get("currency.base_code"))


def base_currency() -> Currency:
    currency = get_currency(base_currency_code())
    if currency is None:
        raise RateUnavailable(f"Asosiy valyuta {base_currency_code()} jadvalda yo'q")
    return currency


def rates_queryset() -> QuerySet[ExchangeRate]:
    return ExchangeRate.objects.select_related("currency", "created_by")


def latest_rate(currency: Currency, on: date | None = None) -> ExchangeRate | None:
    on = on or timezone.localdate()
    return currency.rates.filter(date__lte=on).order_by("-date", "-id").first()


def latest_rates(on: date | None = None) -> dict[str, ExchangeRate | None]:
    """Faol valyutalar (UZS dan tashqari) uchun joriy kurs: {code: ExchangeRate | None}."""
    return {c.code: latest_rate(c, on) for c in active_currencies().exclude(code=QUOTE_CODE)}


RATE_TO_BASE_PLACES = Decimal("0.000000000001")


def rate_to_base(code: str, on: date | None = None) -> Decimal:
    """Ko'paytuvchi k: summa (code) * k = summa (asosiy valyuta). Hujjatlarda snapshot sifatida."""
    code = code.upper()
    base = base_currency_code()
    if code == base:
        return Decimal(1)
    return (rate_value(code, on) / rate_value(base, on)).quantize(RATE_TO_BASE_PLACES)


def rate_value(code: str, on: date | None = None) -> Decimal:
    """1 birlik `code` necha so'm. UZS → 1. Kurs bo'lmasa RateUnavailable (409)."""
    code = code.upper()
    if code == QUOTE_CODE:
        return Decimal(1)
    currency = get_currency(code)
    if currency is None:
        raise RateUnavailable(f"Noma'lum valyuta: {code}")
    rate = latest_rate(currency, on)
    if rate is None:
        raise RateUnavailable(f"{code} uchun kurs kiritilmagan")
    return rate.rate
