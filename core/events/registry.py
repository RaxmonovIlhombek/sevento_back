from collections import defaultdict
from collections.abc import Callable

Handler = Callable[..., None]
WILDCARD = "*"

_subscribers: dict[str, list[Handler]] = defaultdict(list)


def subscribe(*names: str):
    """Obunachi dekoratori: @subscribe("sale.completed") yoki @subscribe("*") (hammasi)."""

    def decorator(fn: Handler) -> Handler:
        for name in names:
            if fn not in _subscribers[name]:
                _subscribers[name].append(fn)
        return fn

    return decorator


def get_subscribers(name: str) -> list[Handler]:
    return list(_subscribers.get(name, [])) + list(_subscribers.get(WILDCARD, []))


def clear_subscribers() -> None:
    """Faqat testlar uchun."""
    _subscribers.clear()


def snapshot_subscribers() -> dict[str, list[Handler]]:
    return {name: list(handlers) for name, handlers in _subscribers.items()}


def restore_subscribers(saved: dict[str, list[Handler]]) -> None:
    _subscribers.clear()
    for name, handlers in saved.items():
        _subscribers[name].extend(handlers)
