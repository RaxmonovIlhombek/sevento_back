from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import ClassVar, Protocol


@dataclass(frozen=True)
class RateQuote:
    code: str
    rate: Decimal  # 1 birlik = rate UZS
    date: date


class ProviderError(Exception):
    """Manba javob bermadi yoki javobi tushunarsiz."""


class RateProvider(Protocol):
    key: ClassVar[str]
    name: ClassVar[str]

    def fetch_rates(self, codes: Iterable[str]) -> list[RateQuote]: ...


_PROVIDERS: dict[str, type] = {}


def register(provider_cls: type) -> None:
    _PROVIDERS[provider_cls.key] = provider_cls


def get_provider(key: str, **kwargs) -> RateProvider:
    try:
        return _PROVIDERS[key](**kwargs)
    except KeyError:
        raise ProviderError(f"Noma'lum kurs manbai: {key}") from None


def available_providers() -> list[tuple[str, str]]:
    return [(k, cls.name) for k, cls in _PROVIDERS.items()]
