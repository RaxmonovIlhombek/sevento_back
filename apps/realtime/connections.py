"""Foydalanuvchi bo'yicha ochiq ulanishlar soni (limit uchun). Keshda, TTL bilan — jarayon
o'lib qolsa ham hisob abadiy osilib qolmaydi."""

from django.core.cache import cache

PREFIX = "ws:conn:"
TTL = 60 * 60


def register(user_id: int) -> int:
    key = PREFIX + str(user_id)
    cache.add(key, 0, TTL)
    try:
        count = cache.incr(key)
    except ValueError:  # TTL tugab ketgan bo'lsa
        cache.set(key, 1, TTL)
        count = 1
    cache.touch(key, TTL)
    return count


def release(user_id: int) -> None:
    key = PREFIX + str(user_id)
    try:
        if cache.decr(key) <= 0:
            cache.delete(key)
    except ValueError:
        pass


def count(user_id: int) -> int:
    return int(cache.get(PREFIX + str(user_id), 0))
