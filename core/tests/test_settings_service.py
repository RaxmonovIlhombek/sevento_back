from decimal import Decimal

import pytest
from django.core.cache import cache

from core import settings_service
from core.models import OutboxEvent, SystemSetting

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


def test_default_when_not_in_db():
    assert settings_service.get("payments.default_due_days") == 30
    assert settings_service.get("inventory.default_min_quantity") == Decimal("5")
    assert settings_service.get("inventory.allow_negative_stock") is False


def test_unknown_key():
    with pytest.raises(KeyError):
        settings_service.get("nope.key")


def test_set_and_get_with_cache_invalidation(django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        item = settings_service.set(key="payments.default_due_days", value=45)
    assert item["value"] == 45
    assert item["is_overridden"] is True
    assert settings_service.get("payments.default_due_days") == 45
    assert SystemSetting.objects.get(key="payments.default_due_days").value == 45
    assert OutboxEvent.objects.filter(name="setting.changed").count() == 1

    with django_capture_on_commit_callbacks(execute=True):
        settings_service.set(key="payments.default_due_days", value=60)
    assert settings_service.get("payments.default_due_days") == 60


def test_set_wrong_type_rejected():
    with pytest.raises(ValueError):
        settings_service.set(key="payments.default_due_days", value="30 kun")
    with pytest.raises(ValueError):
        settings_service.set(key="inventory.allow_negative_stock", value="yes")
    with pytest.raises(ValueError):
        settings_service.set(key="inventory.costing_method", value="lifo")


def test_decimal_stored_as_string(django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        settings_service.set(key="inventory.default_min_quantity", value="7.5")
    assert SystemSetting.objects.get(key="inventory.default_min_quantity").value == "7.5"
    assert settings_service.get("inventory.default_min_quantity") == Decimal("7.5")


def test_reset_returns_default(django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        settings_service.set(key="payments.default_due_days", value=45)
        item = settings_service.reset(key="payments.default_due_days")
    assert item["is_overridden"] is False
    assert settings_service.get("payments.default_due_days") == 30
