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


# --- 5-bosqich: savdo va to'lov ---


def _capability_users(code: str) -> list[str]:
    """Rollar MB da o'zgaradi: rol nomi emas, huquq bo'yicha foydalanuvchi guruhlari."""
    from apps.accounts import selectors as accounts_selectors  # app registry tayyor bo'lgach

    users = accounts_selectors.users_with_capability(code)
    return [f"user_{pk}" for pk in users.values_list("pk", flat=True)]


def _dashboard_payload(reason: str):
    return lambda e: {"branch_id": e.branch_id, "reason": reason}


route(
    "sale.completed",
    groups=lambda e: _capability_users("dashboard.view"),
    msg_type="dashboard.updated",
    payload=_dashboard_payload("sale.completed"),
)
route(
    "sale.cancelled",
    groups=lambda e: _capability_users("dashboard.view"),
    msg_type="dashboard.updated",
    payload=_dashboard_payload("sale.cancelled"),
)


def _payment_payload(e: Event) -> dict:
    return {  # type: ignore[attr-defined]
        "branch_id": e.branch_id,
        "payment_id": e.payment_id,
        "method": e.method,
        "currency": e.currency,
        "amount": str(e.amount),
        "is_cash": e.is_cash,
        "cashbox_id": e.cashbox_id,
        "customer_id": getattr(e, "customer_id", None),
        "document": {"type": e.document_type, "id": e.document_id},
    }


route("payment.received", groups=_branch_group, payload=_payment_payload)
route("payment.refunded", groups=_branch_group, payload=_payment_payload)


# --- 6-bosqich: nasiya, qarz, kassa smenasi ---

route(
    "payment.received",
    groups=lambda e: _capability_users("dashboard.view"),
    msg_type="dashboard.updated",
    payload=_dashboard_payload("payment.received"),
)


def _debt_changed(e: Event) -> dict:
    return {"branch_id": e.branch_id, "debt_id": e.debt_id, "customer_id": e.customer_id}  # type: ignore[attr-defined]


for _name in ("debt.registered", "debt.settled", "debt.cancelled", "debt.reduced"):
    route(_name, groups=_branch_group, msg_type="debt.changed", payload=_debt_changed)

# buxgalter va rahbar (qarzlarni boshqaradiganlar) — rol nomi emas, huquq
route(
    "debt.overdue",
    groups=lambda e: _capability_users("debts.manage"),
    payload=lambda e: {  # type: ignore[attr-defined]
        "branch_id": e.branch_id,
        "debt_id": e.debt_id,
        "customer_id": e.customer_id,
        "customer_name": e.customer_name,
        "amount_remaining": str(e.amount_remaining),
        "currency": e.currency,
        "due_date": e.due_date.isoformat(),
        "days_overdue": e.days_overdue,
    },
)
route(
    "customer.credit_limit_warning",
    groups=lambda e: _capability_users("debts.manage"),
    payload=lambda e: {  # type: ignore[attr-defined]
        "customer_id": e.customer_id,
        "customer_name": e.customer_name,
        "used_base": str(e.used_base),
        "limit_base": str(e.limit_base),
        "percent": str(e.percent),
        "base_currency": e.base_currency,
    },
)


def _cash_payload(reason: str):
    return lambda e: {"branch_id": e.branch_id, "reason": reason}


route(
    "cash_shift.opened",
    groups=_branch_group,
    msg_type="cash.updated",
    payload=_cash_payload("shift_opened"),
)
route(
    "cash_shift.closed",
    groups=_branch_group,
    msg_type="cash.updated",
    payload=_cash_payload("shift_closed"),
)
route(
    "cash_entry.created",
    groups=_branch_group,
    msg_type="cash.updated",
    payload=_cash_payload("manual_entry"),
)


# --- 7-bosqich: ko'chirish holati ikkala nuqtada jonli ---
# Bitta marshrut — bitta xabar (bitta id): ikkala guruhda bo'lgan foydalanuvchi uni bir marta oladi.


def _transfer_payload(e: Event) -> dict:
    return {  # type: ignore[attr-defined]
        "transfer_id": e.transfer_id,
        "number": e.number,
        "from_branch_id": e.from_branch_id,
        "from_branch_name": e.from_branch_name,
        "to_branch_id": e.to_branch_id,
        "to_branch_name": e.to_branch_name,
        "actor_id": e.actor_id,
    }


def _transfer_branches(e: Event) -> list[str]:
    return [f"branch_{e.from_branch_id}", f"branch_{e.to_branch_id}"]  # type: ignore[attr-defined]


route(
    "transfer.sent",
    groups=_transfer_branches,
    payload=lambda e: {**_transfer_payload(e), "status": "sent", "items_count": e.items_count},  # type: ignore[attr-defined]
)
route(
    "transfer.received",
    # farq bo'lsa rahbar (dashboard) ham xabardor bo'ladi — o'sha xabar, takrorsiz
    groups=lambda e: _transfer_branches(e)
    + (_capability_users("dashboard.view") if e.has_discrepancy else []),  # type: ignore[attr-defined]
    payload=lambda e: {  # type: ignore[attr-defined]
        **_transfer_payload(e),
        "status": "received",
        "has_discrepancy": e.has_discrepancy,
        "discrepancies": [
            {k: d[k] for k in ("product_name", "quantity", "quantity_received")}
            for d in e.discrepancies
        ],
    },
)
route(
    "transfer.cancelled",
    # qoralama qabul qiluvchiga ko'rinmagan — unga faqat jo'natilgani bekor bo'lsa
    groups=lambda e: _transfer_branches(e)
    if e.previous_status == "sent"  # type: ignore[attr-defined]
    else [f"branch_{e.from_branch_id}"],  # type: ignore[attr-defined]
    payload=lambda e: {  # type: ignore[attr-defined]
        **_transfer_payload(e),
        "status": "cancelled",
        "previous_status": e.previous_status,
        "reason": e.reason,
    },
)


# --- qaytarish: savdo ro'yxati (nuqta) va dashboard yangilanadi ---

route(
    "sale_return.completed",
    groups=_branch_group,
    payload=lambda e: {  # type: ignore[attr-defined]
        "branch_id": e.branch_id,
        "return_id": e.return_id,
        "number": e.number,
        "sale_id": e.sale_id,
        "customer_id": e.customer_id,
    },
)
route(
    "sale_return.completed",
    groups=lambda e: _capability_users("dashboard.view"),
    msg_type="dashboard.updated",
    payload=_dashboard_payload("sale_return.completed"),
)


# --- 8-bosqich: fondagi hisobot tayyor / xato — faqat so'ragan foydalanuvchiga ---

route(
    "report.ready",
    groups=_user_group,
    payload=lambda e: {  # type: ignore[attr-defined]
        "job_id": e.job_id,
        "report_key": e.report_key,
        "title": e.title,
        "format": e.format,
        "download_url": e.download_url,
    },
)
route(
    "report.failed",
    groups=_user_group,
    payload=lambda e: {  # type: ignore[attr-defined]
        "job_id": e.job_id,
        "report_key": e.report_key,
        "title": e.title,
        "error": e.error,
    },
)
