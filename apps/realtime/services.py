from django.db import transaction

from . import events, tickets


def issue_ticket(*, user) -> dict:
    ticket, ttl = tickets.issue_ticket(user)
    return {"ticket": ticket, "expires_in": ttl}


def send_notice(*, actor, level: str, message: str) -> None:
    """Hammaga xabar: hodisa → audit + broadcast guruhi."""
    with transaction.atomic():
        events.SystemNoticeSent.publish_from(actor=actor, level=level, message=message)
