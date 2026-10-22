"""SystemSetting ni tipli o'qish/yozish, kesh bilan."""

from typing import Any

from django.core.cache import cache
from django.db import transaction

from . import settings_registry
from .events.system import SettingChanged
from .models import SystemSetting

CACHE_TTL = 60
_MISSING = object()


def _cache_key(key: str) -> str:
    return f"setting:{key}"


def get(key: str) -> Any:
    """Sozlama qiymatini (tipga keltirilgan) qaytaradi; MB da yo'q bo'lsa default."""
    definition = settings_registry.get_def(key)
    cached = cache.get(_cache_key(key), _MISSING)
    if cached is _MISSING:
        row = SystemSetting.objects.filter(key=key).values_list("value", flat=True).first()
        cached = row if row is not None else definition.to_json(definition.default)
        cache.set(_cache_key(key), cached, CACHE_TTL)
    return definition.coerce(cached)


def get_all() -> list[dict]:
    rows = {s.key: s for s in SystemSetting.objects.select_related("updated_by")}
    result = []
    for d in settings_registry.all_defs():
        row = rows.get(d.key)
        result.append(
            {
                "key": d.key,
                "type": d.type,
                "choices": list(d.choices),
                "description": d.description,
                "default": d.to_json(d.default),
                "value": row.value if row else d.to_json(d.default),
                "is_overridden": row is not None,
                "updated_at": row.updated_at if row else None,
                "updated_by": row.updated_by.username if row and row.updated_by else None,
            }
        )
    return result


def set(*, key: str, value: Any, actor=None) -> dict:  # noqa: A001
    definition = settings_registry.get_def(key)
    coerced = definition.coerce(value)  # ValueError → view 400 ga aylantiradi
    json_value = definition.to_json(coerced)
    with transaction.atomic():
        row = SystemSetting.objects.select_for_update().filter(key=key).first()
        old = row.value if row else definition.to_json(definition.default)
        if row is None:
            row = SystemSetting.objects.create(key=key, value=json_value, updated_by=actor)
        else:
            row.value = json_value
            row.updated_by = actor
            row.save(update_fields=["value", "updated_by", "updated_at"])
        SettingChanged.publish_from(
            actor=actor, key=key, old_value=old, new_value=json_value, setting_id=row.pk
        )
        transaction.on_commit(lambda: cache.delete(_cache_key(key)))
    return next(item for item in get_all() if item["key"] == key)


def reset(*, key: str, actor=None) -> dict:
    """Qiymatni o'chirib default ga qaytaradi."""
    definition = settings_registry.get_def(key)
    with transaction.atomic():
        row = SystemSetting.objects.select_for_update().filter(key=key).first()
        if row is not None:
            SettingChanged.publish_from(
                actor=actor,
                key=key,
                old_value=row.value,
                new_value=definition.to_json(definition.default),
                setting_id=row.pk,
            )
            row.delete()
        transaction.on_commit(lambda: cache.delete(_cache_key(key)))
    return next(item for item in get_all() if item["key"] == key)
