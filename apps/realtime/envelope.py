"""Yagona WebSocket xabar konverti: {type, payload, timestamp}."""

from typing import Any

from django.utils import timezone


def envelope(msg_type: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "type": msg_type,
        "payload": payload or {},
        "timestamp": timezone.localtime().isoformat(timespec="milliseconds"),
    }
