"""Valyuta kursi manbalari (adapter naqshi).

Yangi manba: RateProvider ni amalga oshirib register() qilinadi.
"""

from .base import ProviderError, RateProvider, RateQuote, get_provider, register
from .cbu import CbuRateProvider
from .manual import ManualRateProvider

register(CbuRateProvider)
register(ManualRateProvider)

__all__ = [
    "ProviderError",
    "RateProvider",
    "RateQuote",
    "get_provider",
    "register",
    "CbuRateProvider",
    "ManualRateProvider",
]
