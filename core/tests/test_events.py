from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import transaction
from django.utils import timezone

from core.events import (
    Event,
    clear_subscribers,
    publish,
    redispatch_pending,
    restore_subscribers,
    snapshot_subscribers,
    subscribe,
)
from core.events.base import _EVENT_CLASSES
from core.exceptions import EventOutsideTransaction
from core.models import OutboxEvent


@dataclass(frozen=True, kw_only=True)
class ThingHappened(Event):
    name = "test.thing_happened"
    aggregate_type = "thing"
    aggregate_id_field = "thing_id"

    thing_id: int
    amount: Decimal
    note: str | None = None


@pytest.fixture(autouse=True)
def _isolated_subscribers():
    saved = snapshot_subscribers()
    clear_subscribers()
    yield
    restore_subscribers(saved)


@pytest.fixture
def received():
    box = []
    subscribe("test.thing_happened")(lambda e: box.append(e))
    return box


pytestmark = pytest.mark.django_db


@pytest.mark.django_db(transaction=True)
def test_publish_outside_transaction_raises():
    with pytest.raises(EventOutsideTransaction):
        publish(ThingHappened(thing_id=1, amount=Decimal("1")))


def test_event_registered_by_name():
    assert _EVENT_CLASSES["test.thing_happened"] is ThingHappened


def test_dispatch_after_commit(received, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        with transaction.atomic():
            row = publish(ThingHappened(thing_id=5, amount=Decimal("12.50"), actor_id=3))
            assert received == []  # commit dan oldin hech narsa ketmaydi
            assert OutboxEvent.objects.get(pk=row.pk).status == OutboxEvent.Status.PENDING

    assert len(received) == 1
    assert received[0].thing_id == 5
    row.refresh_from_db()
    assert row.status == OutboxEvent.Status.DISPATCHED
    assert row.attempts == 1
    assert row.aggregate_type == "thing"
    assert row.aggregate_id == 5
    assert row.actor_id == 3
    assert row.payload == {"thing_id": 5, "amount": "12.50", "note": None}


def test_rollback_sends_nothing(received, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        with pytest.raises(RuntimeError):
            with transaction.atomic():
                publish(ThingHappened(thing_id=1, amount=Decimal("1")))
                raise RuntimeError("rollback")
    assert received == []
    assert OutboxEvent.objects.count() == 0


def test_failing_subscriber_does_not_block_others(django_capture_on_commit_callbacks):
    calls = []

    @subscribe("test.thing_happened")
    def bad(event):
        raise ValueError("boom")

    @subscribe("test.thing_happened")
    def good(event):
        calls.append(event)

    with django_capture_on_commit_callbacks(execute=True):
        with transaction.atomic():
            row = publish(ThingHappened(thing_id=1, amount=Decimal("1")))

    assert len(calls) == 1
    row.refresh_from_db()
    assert row.status == OutboxEvent.Status.FAILED
    assert "boom" in row.last_error


def test_wildcard_subscriber(django_capture_on_commit_callbacks):
    seen = []
    subscribe("*")(lambda e: seen.append(e.name))
    with django_capture_on_commit_callbacks(execute=True):
        with transaction.atomic():
            publish(ThingHappened(thing_id=1, amount=Decimal("1")))
    assert seen == ["test.thing_happened"]


def test_actor_taken_from_context(received, django_capture_on_commit_callbacks):
    from core.context import reset_context, update_context

    token = update_context(actor_id=42)
    try:
        with django_capture_on_commit_callbacks(execute=True):
            with transaction.atomic():
                row = publish(ThingHappened(thing_id=1, amount=Decimal("1")))
    finally:
        reset_context(token)
    assert received[0].actor_id == 42
    assert row.actor_id == 42


def test_redispatch_pending_rebuilds_event_with_types(received):
    with transaction.atomic():
        row = publish(ThingHappened(thing_id=9, amount=Decimal("3.25"), note="x"))
    # on_commit testda ishlamaydi → pending qoladi; "eski" qilib qo'yamiz
    OutboxEvent.objects.filter(pk=row.pk).update(created_at=timezone.now() - timedelta(minutes=5))

    assert redispatch_pending() == 1
    assert len(received) == 1
    event = received[0]
    assert isinstance(event, ThingHappened)
    assert event.amount == Decimal("3.25")
    assert isinstance(event.amount, Decimal)
    assert event.note == "x"
    row.refresh_from_db()
    assert row.status == OutboxEvent.Status.DISPATCHED


def test_redispatch_restores_request_context(django_capture_on_commit_callbacks):
    from core.context import RequestContext, get_context, reset_context, set_context

    seen = []
    subscribe("test.thing_happened")(lambda e: seen.append(get_context()))
    token = set_context(RequestContext(request_id="req-7", ip="10.0.0.1", user_agent="UA"))
    try:
        with transaction.atomic():
            row = publish(ThingHappened(thing_id=1, amount=Decimal("1"), actor_id=5))
    finally:
        reset_context(token)
    OutboxEvent.objects.filter(pk=row.pk).update(created_at=timezone.now() - timedelta(minutes=5))

    assert redispatch_pending() == 1
    assert seen[0] == RequestContext(request_id="req-7", actor_id=5, ip="10.0.0.1", user_agent="UA")
    assert get_context().request_id == ""


def test_redispatch_skips_fresh_pending(received):
    with transaction.atomic():
        publish(ThingHappened(thing_id=9, amount=Decimal("1")))
    assert redispatch_pending() == 0
    assert received == []


def test_redispatch_gives_up_after_max_attempts():
    subscribe("test.thing_happened")(lambda e: (_ for _ in ()).throw(ValueError("x")))
    with transaction.atomic():
        row = publish(ThingHappened(thing_id=1, amount=Decimal("1")))
    OutboxEvent.objects.filter(pk=row.pk).update(
        status=OutboxEvent.Status.FAILED, attempts=5, created_at=timezone.now() - timedelta(hours=1)
    )
    assert redispatch_pending() == 0
