from celery import shared_task

from . import services


@shared_task(name="currency.fetch_rates")
def fetch_rates() -> int:
    """Celery Beat (jadval MB da): provayderdan kurslarni oladi."""
    return len(services.fetch_rates())
