import logging
from dataclasses import replace
from datetime import timedelta

from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from ..context import RequestContext, get_context, reset_context, set_context
from ..exceptions import EventOutsideTransaction
from ..models import OutboxEvent
from .base import Event
from .registry import get_subscribers

log = logging.getLogger("core.events")

MAX_ATTEMPTS = 5


def publish(event: Event) -> OutboxEvent:
    """Hodisani outbox ga yozadi va commit dan keyin tarqatadi.

    Faqat transaction.atomic ichida chaqiriladi: MB ga yozilmagan narsa haqida xabar ketmasin.
    """
    connection = transaction.get_connection()
    if not connection.in_atomic_block:
        raise EventOutsideTransaction(
            f"{event.name}: publish() faqat transaction.atomic ichida chaqirilishi kerak"
        )
    ctx = get_context()
    if event.actor_id is None and ctx.actor_id is not None:
        event = replace(event, actor_id=ctx.actor_id)

    row = OutboxEvent.objects.create(
        name=event.name,
        aggregate_type=event.aggregate_type,
        aggregate_id=event.aggregate_id,
        payload=event.json_payload(),
        actor_id=event.actor_id,
        branch_id=event.branch_id,
        request_id=ctx.request_id,
        ip=ctx.ip or "",
        user_agent=ctx.user_agent,
        occurred_at=event.occurred_at,
    )
    ctx = replace(ctx, actor_id=event.actor_id)
    transaction.on_commit(lambda: dispatch(row.pk, event, ctx))
    return row


def dispatch(outbox_id: int, event: Event, ctx: RequestContext | None = None) -> bool:
    """Obunachilarni chaqiradi. Bittasi xato bersa qolganlari baribir ishlaydi.

    `ctx` — hodisa chiqarilgan so'rov konteksti (audit uchun); Celery dan qayta tarqatilganda
    outbox qatoridan tiklanadi.
    """
    errors: list[str] = []
    token = set_context(ctx) if ctx is not None else None
    try:
        for handler in get_subscribers(event.name):
            try:
                handler(event)
            except Exception as exc:  # noqa: BLE001 — obunachi xatosi asosiy oqimni buzmasin
                log.exception(
                    "Hodisa obunachisi xato berdi: %s ← %s", handler.__qualname__, event.name
                )
                errors.append(f"{handler.__module__}.{handler.__qualname__}: {exc}"[:500])
    finally:
        if token is not None:
            reset_context(token)

    ok = not errors
    OutboxEvent.objects.filter(pk=outbox_id).update(
        status=OutboxEvent.Status.DISPATCHED if ok else OutboxEvent.Status.FAILED,
        attempts=F("attempts") + 1,
        dispatched_at=timezone.now() if ok else None,
        last_error="\n".join(errors)[:2000],
    )
    return ok


def redispatch_pending(*, older_than_seconds: int = 60, limit: int = 200) -> int:
    """Jo'natilmay qolgan (pending) yoki xato bo'lgan hodisalarni qayta tarqatadi (Celery)."""
    threshold = timezone.now() - timedelta(seconds=older_than_seconds)
    rows = OutboxEvent.objects.filter(
        Q(status=OutboxEvent.Status.PENDING, created_at__lt=threshold)
        | Q(status=OutboxEvent.Status.FAILED, attempts__lt=MAX_ATTEMPTS)
    ).order_by("id")[:limit]

    count = 0
    for row in rows:
        try:
            event = Event.from_outbox(row)
        except Exception as exc:  # noqa: BLE001
            log.exception("Outbox hodisasini tiklab bo'lmadi: %s", row)
            OutboxEvent.objects.filter(pk=row.pk).update(
                status=OutboxEvent.Status.FAILED,
                attempts=F("attempts") + 1,
                last_error=str(exc)[:2000],
            )
            continue
        ctx = RequestContext(
            request_id=row.request_id,
            actor_id=row.actor_id,
            ip=row.ip or None,
            user_agent=row.user_agent,
        )
        dispatch(row.pk, event, ctx)
        count += 1
    return count
