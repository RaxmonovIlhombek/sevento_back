"""To'lov provayderlari reyestri.

Yangi provayder: klass + register(); PaymentMethod.provider = key.
"""

from ..exceptions import ProviderUnavailable
from .base import PaymentProvider, ProviderResult
from .manual import ManualProvider

_PROVIDERS: dict[str, PaymentProvider] = {}


def register(provider: PaymentProvider) -> None:
    _PROVIDERS[provider.key] = provider


def get_provider(key: str) -> PaymentProvider:
    try:
        return _PROVIDERS[key]
    except KeyError:
        raise ProviderUnavailable(f"To'lov provayderi ulanmagan: {key}") from None


def provider_choices() -> list[tuple[str, str]]:
    return [(p.key, p.name) for p in _PROVIDERS.values()]


register(ManualProvider())

__all__ = ["PaymentProvider", "ProviderResult", "get_provider", "provider_choices", "register"]
