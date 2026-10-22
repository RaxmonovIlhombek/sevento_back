"""Bir martalik WebSocket ticketlari.

REST orqali olinadi, ulanishdan keyin birinchi xabarda yuboriladi; URL va sarlavhalarga yozilmaydi.
Redis da (django-redis) atomar GETDEL bilan olinadi; boshqa kesh (testlar) uchun get+delete.
"""

import secrets

from django.core.cache import cache

from . import conf

PREFIX = "ws:ticket:"


def _redis():
    try:
        from django_redis import get_redis_connection

        if type(cache).__module__.startswith("django_redis"):
            return get_redis_connection("default")
    except ImportError:
        pass
    return None


def issue_ticket(user) -> tuple[str, int]:
    """(ticket, expires_in) — ticket foydalanuvchi id siga bog'lanadi."""
    ttl = conf.get("TICKET_TTL")
    ticket = secrets.token_urlsafe(32)
    redis = _redis()
    if redis is not None:
        redis.set(cache.make_key(PREFIX + ticket), str(user.pk), ex=ttl)
    else:
        cache.set(PREFIX + ticket, user.pk, ttl)
    return ticket, ttl


def consume_ticket(ticket: str) -> int | None:
    """Ticketni bir marta ishlatadi: user_id yoki None (yo'q / eskirgan / ishlatilgan)."""
    if not ticket or len(ticket) > 128:
        return None
    redis = _redis()
    if redis is not None:
        value = redis.getdel(cache.make_key(PREFIX + ticket))
        return int(value) if value else None
    key = PREFIX + ticket
    value = cache.get(key)
    if value is None:
        return None
    cache.delete(key)
    return int(value)
