from dataclasses import dataclass

from core.events import Event


@dataclass(frozen=True, kw_only=True)
class SystemNoticeSent(Event):
    """Rahbar hammaga xabar yubordi (broadcast)."""

    name = "system.notice"
    aggregate_type = "system"

    level: str  # info | warning | error
    message: str
