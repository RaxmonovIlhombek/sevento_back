"""Kirim xarajatlarini tovar qatorlariga taqsimlash (strategiya naqshi).

Yangi usul (masalan og'irlik bo'yicha): AllocationStrategy ni amalga oshirib register() qilinadi
va AllocationMethod ga qo'shiladi.
"""

from .base import AllocationLine, AllocationStrategy, distribute
from .strategies import ByQuantity, ByValue

_STRATEGIES: dict[str, AllocationStrategy] = {}


def register(strategy: AllocationStrategy) -> None:
    _STRATEGIES[strategy.key] = strategy


def get_strategy(key: str) -> AllocationStrategy:
    try:
        return _STRATEGIES[key]
    except KeyError:
        raise KeyError(f"Noma'lum taqsimlash usuli: {key}") from None


register(ByValue())
register(ByQuantity())

__all__ = ["AllocationLine", "AllocationStrategy", "distribute", "get_strategy", "register"]
