"""So'rov konteksti: request_id, kim (actor), qayerdan (ip, user_agent).

Middleware o'rnatadi, service lar va audit obunachisi o'qiydi. contextvars asosida,
shuning uchun sync va async kodda, Celery ichida ham xavfsiz (Celery da bo'sh bo'ladi).
"""

from contextvars import ContextVar, Token
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class RequestContext:
    request_id: str = ""
    actor_id: int | None = None
    ip: str | None = None
    user_agent: str = ""


_EMPTY = RequestContext()
_context: ContextVar[RequestContext | None] = ContextVar("sevento_request_context", default=None)


def get_context() -> RequestContext:
    return _context.get() or _EMPTY


def set_context(ctx: RequestContext) -> Token:
    return _context.set(ctx)


def update_context(**changes) -> Token:
    return _context.set(replace(get_context(), **changes))


def reset_context(token: Token) -> None:
    _context.reset(token)
