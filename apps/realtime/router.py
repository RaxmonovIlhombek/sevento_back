"""Domen hodisasi → WebSocket guruhlari + qisqartirilgan payload.

Yangi hodisa uchun bitta `route(...)` qatori qo'shiladi. Payload faqat ekranni yangilash uchun
yetarli minimal maydonlar (tannarx kabi sezgir narsalar yo'q — branch guruhida sotuvchi ham bor).
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from core.events import Event

from .envelope import envelope

log = logging.getLogger("realtime")

BROADCAST = "broadcast"

GroupsFn = Callable[[Event], list[str]]
PayloadFn = Callable[[Event], dict | None]


@dataclass(frozen=True)
class Route:
    groups: GroupsFn
    msg_type: str
    payload: PayloadFn
    handler: str = "notify"  # consumer metodi: notify | revoke


@dataclass(frozen=True)
class Outgoing:
    group: str
    message: dict
    handler: str


_ROUTES: dict[str, list[Route]] = {}


def route(
    event_name: str,
    *,
    groups: GroupsFn,
    msg_type: str | None = None,
    payload: PayloadFn = lambda e: e.json_payload(),
    handler: str = "notify",
) -> None:
    _ROUTES.setdefault(event_name, []).append(
        Route(groups=groups, msg_type=msg_type or event_name, payload=payload, handler=handler)
    )


def resolve(event: Event) -> list[Outgoing]:
    outgoing: list[Outgoing] = []
    for r in _ROUTES.get(event.name, []):
        payload = r.payload(event)
        if payload is None:  # marshrut bu holatda xabar yubormaslikka qaror qildi
            continue
        message = envelope(r.msg_type, payload)
        for group in r.groups(event):
            outgoing.append(Outgoing(group=group, message=message, handler=r.handler))
    return outgoing


def send_to_groups(groups: list[str], message: dict, handler: str = "notify") -> None:
    """Sinxron kontekstdan (on_commit, Celery, view) guruhlarga yuborish."""
    layer = get_channel_layer()
    if layer is None:
        return
    send = async_to_sync(layer.group_send)
    for group in groups:
        send(group, {"type": handler, "message": message})


def forward_event(event: Event) -> int:
    """Obunachi chaqiradi: hodisani marshrutlab guruhlarga yuboradi; yuborilganlar soni."""
    sent = 0
    for out in resolve(event):
        try:
            send_to_groups([out.group], out.message, out.handler)
            sent += 1
        except Exception:  # noqa: BLE001 — channel layer yo'q bo'lsa ham asosiy oqim buzilmasin
            log.exception("WebSocket ga yuborib bo'lmadi: %s → %s", event.name, out.group)
    return sent


# --- Marshrutlar (1–2-bosqich). Keyingi bosqichlar o'z app larida shu funksiya bilan qo'shadi. ---

ACCESS_FIELDS = {"role_id", "branch_ids", "is_active"}


def _user_group(e: Event) -> list[str]:
    return [f"user_{e.user_id}"]  # type: ignore[attr-defined]


def _revoke_if_access_changed(e: Event) -> dict | None:
    changes = getattr(e, "changes", {}) or {}
    if not ACCESS_FIELDS & set(changes):
        return None
    if changes.get("is_active", {}).get("new") is False:
        return None  # user.deactivated alohida yuboradi
    return {"reason": "permissions_changed"}


route(
    "user.deactivated",
    groups=_user_group,
    msg_type="session.revoked",
    payload=lambda e: {"reason": "deactivated"},
    handler="revoke",
)
route(
    "user.updated",
    groups=_user_group,
    msg_type="session.revoked",
    payload=_revoke_if_access_changed,
    handler="revoke",
)
route(
    "user.password_changed",
    groups=_user_group,
    msg_type="session.revoked",
    payload=lambda e: None if e.by_self else {"reason": "password_changed"},  # type: ignore[attr-defined]
    handler="revoke",
)
route(
    "role.updated",
    groups=lambda e: [f"role_{e.code}"],  # type: ignore[attr-defined]
    msg_type="session.revoked",
    payload=lambda e: {"reason": "permissions_changed"}
    if "capabilities" in (e.changes or {})
    else None,  # type: ignore[attr-defined]
    handler="revoke",
)
route(
    "system.notice",
    groups=lambda e: [BROADCAST],
    payload=lambda e: {"level": e.level, "message": e.message},
)  # type: ignore[attr-defined]
route(
    "currency.rate_updated",
    groups=lambda e: [BROADCAST],
    payload=lambda e: {"rates": e.rates, "source": e.source},  # type: ignore[attr-defined]
)


def _branch_group(e: Event) -> list[str]:
    return [f"branch_{e.branch_id}"] if e.branch_id else []


route(
    "stock.changed",
    groups=_branch_group,
    # tannarx yo'q: branch guruhida sotuvchi ham bor
    payload=lambda e: {  # type: ignore[attr-defined]
        "branch_id": e.branch_id,
        "product_id": e.product_id,
        "quantity": str(e.quantity_after),
        "delta": str(e.delta),
        "movement_type": e.movement_type,
        "document": {"type": e.document_type, "id": e.document_id, "number": e.document_number},
    },
)
route(
    "stock.below_minimum",
    groups=_branch_group,
    payload=lambda e: {  # type: ignore[attr-defined]
        "branch_id": e.branch_id,
        "product_id": e.product_id,
        "product_name": e.product_name,
        "quantity": str(e.quantity),
        "min_quantity": str(e.min_quantity),
        "unit": e.unit,
    },
)
