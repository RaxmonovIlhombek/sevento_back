from celery import shared_task

from . import services


@shared_task(name="payments.detect_overdue_debts")
def detect_overdue_debts() -> int:
    """Celery Beat (jadval MB da, default har kuni 08:05): muddati o'tgan qarzlar."""
    return services.detect_overdue_debts()
