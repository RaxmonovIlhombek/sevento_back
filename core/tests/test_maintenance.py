"""Fon vazifalari (outbox qayta jo'natish, tozalash), davriy vazifalar jadvali, health holati."""

from datetime import timedelta
from unittest import mock

import pytest
from django.utils import timezone
from django_celery_beat.models import PeriodicTask
from rest_framework.test import APIClient

from core import tasks
from core.models import IdempotencyRecord, OutboxEvent
from core.scheduling import all_periodic_tasks, ensure_periodic_tasks

pytestmark = pytest.mark.django_db


def _outbox(**kwargs) -> OutboxEvent:
    defaults = {"name": "user.created", "payload": {}, "occurred_at": timezone.now()}
    return OutboxEvent.objects.create(**{**defaults, **kwargs})


def test_cleanup_removes_only_old_records(owner):
    now = timezone.now()
    old_key = IdempotencyRecord.objects.create(key="old", user=owner, method="POST", path="/x/")
    fresh_key = IdempotencyRecord.objects.create(key="new", user=owner, method="POST", path="/x/")
    IdempotencyRecord.objects.filter(pk=old_key.pk).update(created_at=now - timedelta(hours=25))
    old_sent = _outbox(status=OutboxEvent.Status.DISPATCHED, dispatched_at=now - timedelta(days=31))
    recent_sent = _outbox(status=OutboxEvent.Status.DISPATCHED, dispatched_at=now)
    pending = _outbox(status=OutboxEvent.Status.PENDING)

    result = tasks.cleanup()

    assert result == {"idempotency_deleted": 1, "outbox_deleted": 1}
    assert list(IdempotencyRecord.objects.values_list("pk", flat=True)) == [fresh_key.pk]
    remaining = set(OutboxEvent.objects.values_list("pk", flat=True))
    assert remaining == {recent_sent.pk, pending.pk}
    assert old_sent.pk not in remaining


def test_redispatch_outbox_task_marks_failed_unknown_event():
    row = _outbox(name="unknown.event", status=OutboxEvent.Status.PENDING)
    OutboxEvent.objects.filter(pk=row.pk).update(created_at=timezone.now() - timedelta(minutes=5))

    assert tasks.redispatch_outbox() == 0
    row.refresh_from_db()
    assert row.status == OutboxEvent.Status.FAILED
    assert row.attempts == 1 and "Noma'lum hodisa" in row.last_error


def test_ensure_periodic_tasks_is_idempotent_and_keeps_admin_changes():
    expected = len(all_periodic_tasks())
    assert ensure_periodic_tasks() == expected
    task = PeriodicTask.objects.get(task="core.cleanup")
    task.enabled = False
    task.save()

    assert ensure_periodic_tasks() == 0
    assert PeriodicTask.objects.filter(task="core.cleanup").count() == 1
    task.refresh_from_db()
    assert task.enabled is False
    assert task.crontab.timezone.key == "Asia/Tashkent"


def test_health_reports_database_failure():
    with mock.patch("core.views.connection.cursor", side_effect=RuntimeError("db down")):
        response = APIClient().get("/api/v1/health/")
    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "db": False, "redis": True}


def test_health_reports_cache_failure():
    with mock.patch("core.views.cache.set", side_effect=ConnectionError("redis down")):
        response = APIClient().get("/api/v1/health/")
    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "db": True, "redis": False}
