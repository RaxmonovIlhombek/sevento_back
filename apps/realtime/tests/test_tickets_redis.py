"""Ticket — production yo'li: Redis (django-redis), atomar GETDEL. Redis bo'lmasa o'tkaziladi."""

import os

import pytest
from django.core.cache import caches
from django.test import override_settings

from apps.realtime import tickets

REDIS_URL = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/1")
REDIS_CACHE = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        "KEY_PREFIX": "sevento-test",
    }
}


@pytest.fixture
def redis_cache():
    with override_settings(CACHES=REDIS_CACHE):
        cache = caches["default"]
        try:
            cache.set("ping", 1, 5)
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"Redis yo'q: {exc}")
        yield cache
        cache.close()


def test_ticket_single_use_via_redis_getdel(redis_cache, monkeypatch):
    monkeypatch.setattr(tickets, "cache", redis_cache)
    user = type("U", (), {"pk": 42})()
    ticket, ttl = tickets.issue_ticket(user)
    assert ttl > 0
    assert tickets._redis() is not None
    assert tickets.consume_ticket(ticket) == 42
    assert tickets.consume_ticket(ticket) is None  # bir marta


def test_ticket_rejects_garbage(redis_cache, monkeypatch):
    monkeypatch.setattr(tickets, "cache", redis_cache)
    assert tickets.consume_ticket("") is None
    assert tickets.consume_ticket("x" * 200) is None
    assert tickets.consume_ticket("yo'q-ticket") is None
