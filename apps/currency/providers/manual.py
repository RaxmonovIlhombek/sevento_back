from collections.abc import Iterable

from .base import RateQuote


class ManualRateProvider:
    """Kurs faqat qo'lda kiritiladi — avtomatik yangilash hech narsa qilmaydi."""

    key = "manual"
    name = "Qo'lda kiritish"

    def fetch_rates(self, codes: Iterable[str]) -> list[RateQuote]:
        return []
