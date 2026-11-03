"""Kirish hodisalarini (muvaffaqiyatli va xato) alohida jadvalga yozadi.

Hodisalar nomi bo'yicha obuna bo'linadi — accounts ichki qatlamini import qilish shart emas.
IP va User-Agent hodisa chiqarilgan so'rov kontekstidan olinadi.
"""

from core.context import get_context
from core.events import Event, subscribe

from .devices import parse_user_agent
from .models import LoginEvent


def _record(event: Event, *, success: bool) -> None:
    ctx = get_context()
    payload = event.payload()
    LoginEvent.objects.create(
        user_id=payload.get("user_id") if success else None,
        username=str(payload.get("username", ""))[:150],
        success=success,
        reason="" if success else str(payload.get("reason", ""))[:20],
        ip=(ctx.ip or "")[:45],
        user_agent=ctx.user_agent,
        created_at=event.occurred_at,
        **parse_user_agent(ctx.user_agent),
    )


@subscribe("user.logged_in")
def record_login(event: Event) -> None:
    _record(event, success=True)


@subscribe("user.login_failed")
def record_failed_login(event: Event) -> None:
    _record(event, success=False)
