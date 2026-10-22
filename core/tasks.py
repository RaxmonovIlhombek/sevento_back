from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from .events import redispatch_pending
from .models import IdempotencyRecord, OutboxEvent


@shared_task(name="core.redispatch_outbox")
def redispatch_outbox() -> int:
    return redispatch_pending()


@shared_task(name="core.cleanup")
def cleanup() -> dict:
    now = timezone.now()
    idem, _ = IdempotencyRecord.objects.filter(created_at__lt=now - timedelta(hours=24)).delete()
    outbox, _ = OutboxEvent.objects.filter(
        status=OutboxEvent.Status.DISPATCHED, dispatched_at__lt=now - timedelta(days=30)
    ).delete()
    return {"idempotency_deleted": idem, "outbox_deleted": outbox}
