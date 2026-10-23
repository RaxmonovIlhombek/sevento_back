"""Yagona WebSocket xabar konverti: {id, type, payload, timestamp}.

`id` — bitta xabar bir nechta guruh orqali bir ulanishga kelsa (masalan ko'chirish ikkala nuqta
guruhiga yuboriladi, rahbar esa ikkalasida ham bor) mijoz uni bir marta qayta ishlaydi.
"""

import uuid
from typing import Any

from django.utils import timezone


def envelope(msg_type: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "id": uuid.uuid4().hex,
        "type": msg_type,
        "payload": payload or {},
        "timestamp": timezone.localtime().isoformat(timespec="milliseconds"),
    }
