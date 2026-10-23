"""Tannarx usullari (strategiya naqshi). Hozir FIFO; o'rtacha tannarx — yangi klass + register().

Tanlov: SystemSetting["inventory.costing_method"].
"""

from core import settings_service

from .base import CostingStrategy
from .fifo import FifoStrategy

_STRATEGIES: dict[str, type] = {}


def register(strategy_cls: type) -> None:
    _STRATEGIES[strategy_cls.key] = strategy_cls


def get_strategy(key: str | None = None) -> CostingStrategy:
    key = key or str(settings_service.get("inventory.costing_method"))
    try:
        return _STRATEGIES[key]()
    except KeyError:
        raise KeyError(f"Noma'lum tannarx usuli: {key}") from None


register(FifoStrategy)

__all__ = ["CostingStrategy", "FifoStrategy", "get_strategy", "register"]
