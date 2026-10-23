"""Valyuta va kurs: yozish, provayderdan olish, konvertatsiya."""

import logging
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone

from core import settings_service
from core.exceptions import BusinessRuleError

from . import events, selectors
from .models import QUOTE_CODE, Currency, ExchangeRate
from .providers import ProviderError, get_provider

log = logging.getLogger("currency")

MONEY_PLACES = Decimal("0.0001")
RATE_PLACES = Decimal("0.000001")


class ProviderUnavailable(BusinessRuleError):
    status_code = 503
    code = "rate_provider_unavailable"
    message = "Kurs manbai javob bermadi"


# --- valyutalar ---

TRACKED = ("code", "name", "symbol", "decimal_places", "is_active", "sort_order")


def create_currency(*, actor, **fields) -> Currency:
    fields["code"] = fields["code"].upper()
    with transaction.atomic():
        currency = Currency.objects.create(**fields)
        events.CurrencyCreated.publish_from(
            actor=actor, currency_id=currency.pk, code=currency.code
        )
    return currency


def update_currency(*, actor, currency: Currency, **fields) -> Currency:
    if "code" in fields and fields["code"].upper() != currency.code:
        raise BusinessRuleError("Valyuta kodini o'zgartirib bo'lmaydi", code="currency_code_locked")
    fields.pop("code", None)
    if fields.get("is_active") is False and currency.code in (
        QUOTE_CODE,
        selectors.base_currency_code(),
    ):
        raise BusinessRuleError(
            "Asosiy va so'm valyutasini o'chirib bo'lmaydi", code="currency_required"
        )
    with transaction.atomic():
        changes = {}
        for name, value in fields.items():
            old = getattr(currency, name)
            if old != value:
                changes[name] = {"old": old, "new": value}
                setattr(currency, name, value)
        currency.save()
        if changes:
            events.CurrencyUpdated.publish_from(
                actor=actor, currency_id=currency.pk, code=currency.code, changes=changes
            )
    return currency


# --- kurslar ---


def _upsert_rate(currency: Currency, rate: Decimal, day: date, source: str, actor) -> ExchangeRate:
    rate = Decimal(rate).quantize(RATE_PLACES, rounding=ROUND_HALF_UP)
    if rate <= 0:
        raise BusinessRuleError("Kurs musbat bo'lishi kerak", code="invalid_rate", status_code=400)
    row, _ = ExchangeRate.objects.update_or_create(
        currency=currency,
        date=day,
        defaults={"rate": rate, "source": source, "created_by": actor},
    )
    return row


def set_rate(*, actor, currency: Currency, rate: Decimal, day: date | None = None) -> ExchangeRate:
    """Qo'lda kurs: shu kun uchun CBU kursini ham almashtiradi."""
    if currency.is_quote:
        raise BusinessRuleError(
            "So'm uchun kurs kiritilmaydi", code="quote_currency", status_code=400
        )
    day = day or timezone.localdate()
    with transaction.atomic():
        row = _upsert_rate(currency, rate, day, ExchangeRate.Source.MANUAL, actor)
        events.RateUpdated.publish_from(
            actor=actor,
            source=ExchangeRate.Source.MANUAL,
            rates=[{"currency": currency.code, "rate": str(row.rate), "date": day.isoformat()}],
        )
    return row


def fetch_rates(*, actor=None, provider_key: str | None = None) -> list[ExchangeRate]:
    """Provayderdan faol valyutalar kursini oladi (Celery Beat yoki 'Hozir yangilash')."""
    key = provider_key or str(settings_service.get("currency.rate_provider"))
    provider = get_provider(key)
    currencies = {c.code: c for c in selectors.active_currencies().exclude(code=QUOTE_CODE)}
    if not currencies:
        return []
    try:
        quotes = provider.fetch_rates(currencies.keys())
    except ProviderError as exc:
        log.warning("Kurs olinmadi (%s): %s", key, exc)
        raise ProviderUnavailable(str(exc)) from exc

    rows: list[ExchangeRate] = []
    with transaction.atomic():
        for quote in quotes:
            currency = currencies.get(quote.code)
            if currency is None:
                continue
            rows.append(_upsert_rate(currency, quote.rate, quote.date, key, actor))
        if rows:
            events.RateUpdated.publish_from(
                actor=actor,
                source=key,
                rates=[
                    {"currency": r.currency.code, "rate": str(r.rate), "date": r.date.isoformat()}
                    for r in rows
                ],
            )
    return rows


# --- konvertatsiya ---


def convert(amount: Decimal, from_code: str, to_code: str, on: date | None = None) -> Decimal:
    """from → to, shu kundagi kurs bilan (UZS orqali). Natija 4 xona."""
    from_code, to_code = from_code.upper(), to_code.upper()
    if from_code == to_code:
        return Decimal(amount)
    result = (
        Decimal(amount) * selectors.rate_value(from_code, on) / selectors.rate_value(to_code, on)
    )
    return result.quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)


def to_base(amount: Decimal, code: str, on: date | None = None) -> Decimal:
    return convert(amount, code, selectors.base_currency_code(), on)
