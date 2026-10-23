"""O'zbekiston Markaziy banki: https://cbu.uz/uz/arkhiv-kursov-valyut/json/

Javob: [{"Ccy": "USD", "Rate": "12650.45", "Nominal": "1", "Date": "22.10.2026", ...}, ...]
"""

from collections.abc import Iterable
from datetime import datetime
from decimal import Decimal, InvalidOperation

import httpx
from django.conf import settings

from .base import ProviderError, RateQuote

DEFAULT_URL = "https://cbu.uz/uz/arkhiv-kursov-valyut/json/"


class CbuRateProvider:
    key = "cbu"
    name = "O'zbekiston Markaziy banki"

    def __init__(self, transport: httpx.BaseTransport | None = None, timeout: float = 10.0):
        self.url = getattr(settings, "CURRENCY_CBU_URL", DEFAULT_URL)
        self.transport = transport
        self.timeout = timeout

    def fetch_rates(self, codes: Iterable[str]) -> list[RateQuote]:
        wanted = {c.upper() for c in codes}
        try:
            with httpx.Client(transport=self.transport, timeout=self.timeout) as client:
                response = client.get(self.url, headers={"Accept": "application/json"})
                response.raise_for_status()
                items = response.json()
        except httpx.HTTPError as exc:
            raise ProviderError(f"CBU javob bermadi: {exc}") from exc
        except ValueError as exc:
            raise ProviderError("CBU javobi JSON emas") from exc
        if not isinstance(items, list):
            raise ProviderError("CBU javobi ro'yxat emas")

        quotes: list[RateQuote] = []
        for item in items:
            code = str(item.get("Ccy", "")).upper()
            if code not in wanted:
                continue
            try:
                nominal = Decimal(str(item.get("Nominal") or "1"))
                rate = Decimal(str(item["Rate"])) / nominal
                day = datetime.strptime(item["Date"], "%d.%m.%Y").date()
            except (KeyError, InvalidOperation, ValueError, ZeroDivisionError) as exc:
                raise ProviderError(f"CBU yozuvi tushunarsiz: {item}") from exc
            quotes.append(RateQuote(code=code, rate=rate, date=day))
        return quotes
