"""WebSocket consumer: /ws/v1/

Oqim: ulanish qabul qilinadi → 5 s ichida {"type":"auth","payload":{"ticket"}} kutiladi →
ticket tekshiriladi → foydalanuvchi guruhlarga qo'shiladi → auth.ok. Keyin faqat ping/pong.
Server → mijoz xabarlari channel layer orqali: {"type": "notify"|"revoke", "message": {...}}.

Yopish kodlari: 4401 auth yo'q/yaroqsiz, 4403 ruxsat yo'q/faol emas, 4408 auth kutish vaqti
tugadi, 4429 juda ko'p ulanish (docs/realtime.md).
"""

import asyncio
import json
import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from . import conf, connections, tickets
from .envelope import envelope

log = logging.getLogger("realtime")

CLOSE_UNAUTHORIZED = 4401
CLOSE_FORBIDDEN = 4403
CLOSE_AUTH_TIMEOUT = 4408
CLOSE_TOO_MANY = 4429


@database_sync_to_async
def _load_user_for_ticket(ticket: str):
    from apps.accounts import selectors

    user_id = tickets.consume_ticket(ticket)
    if user_id is None:
        return None
    return selectors.get_user(user_id)


@database_sync_to_async
def _groups_for(user) -> list[str]:
    from apps.accounts import selectors

    return selectors.get_realtime_groups(user)


@database_sync_to_async
def _is_active(user_id: int) -> bool:
    from apps.accounts import selectors

    return selectors.is_user_active(user_id)


class RealtimeConsumer(AsyncJsonWebsocketConsumer):
    user_id: int | None = None
    joined: list[str]
    _auth_task: asyncio.Task | None = None
    _recheck_task: asyncio.Task | None = None
    _counted = False

    async def connect(self):
        self.user_id = None
        self.joined = []
        await self.accept()
        self._auth_task = asyncio.create_task(self._auth_timeout())

    async def _auth_timeout(self):
        await asyncio.sleep(conf.get("AUTH_TIMEOUT"))
        if self.user_id is None:
            await self.close(code=CLOSE_AUTH_TIMEOUT)

    async def receive(self, text_data=None, bytes_data=None, **kwargs):
        if text_data is None:
            return
        try:
            content = json.loads(text_data)
        except ValueError:
            log.debug("WS: noto'g'ri JSON")
            return
        await self.receive_json(content)

    async def receive_json(self, content, **kwargs):
        msg_type = content.get("type") if isinstance(content, dict) else None
        if self.user_id is None:
            if msg_type != "auth":
                await self.close(code=CLOSE_UNAUTHORIZED)
                return
            payload = content.get("payload") or {}
            await self._authenticate(str(payload.get("ticket") or ""))
            return
        if msg_type == "ping":
            await self.send_json(envelope("pong"))
            return
        log.debug("WS: noma'lum xabar turi %r (user %s)", msg_type, self.user_id)

    async def _authenticate(self, ticket: str):
        user = await _load_user_for_ticket(ticket) if ticket else None
        if user is None:
            await self.send_json(
                envelope("auth.error", {"code": "invalid_ticket", "message": "Ticket yaroqsiz"})
            )
            await self.close(code=CLOSE_UNAUTHORIZED)
            return
        if not user.is_active:
            await self.close(code=CLOSE_FORBIDDEN)
            return

        count = await database_sync_to_async(connections.register)(user.pk)
        self._counted = True
        self.user_id = user.pk
        if count > conf.get("MAX_CONNECTIONS_PER_USER"):
            await self.close(code=CLOSE_TOO_MANY)
            return

        groups = await _groups_for(user)
        for group in groups:
            await self.channel_layer.group_add(group, self.channel_name)
        self.joined = groups
        if self._auth_task:
            self._auth_task.cancel()
        self._recheck_task = asyncio.create_task(self._recheck_loop())
        await self.send_json(envelope("auth.ok", {"user_id": user.pk, "groups": groups}))

    async def _recheck_loop(self):
        interval = conf.get("USER_RECHECK_INTERVAL")
        while True:
            await asyncio.sleep(interval)
            if self.user_id is not None and not await _is_active(self.user_id):
                await self.close(code=CLOSE_FORBIDDEN)
                return

    async def disconnect(self, code):
        for task in (self._auth_task, self._recheck_task):
            if task:
                task.cancel()
        for group in self.joined:
            await self.channel_layer.group_discard(group, self.channel_name)
        if self.user_id is not None and self._counted:
            await database_sync_to_async(connections.release)(self.user_id)

    # --- channel layer dan keladigan xabarlar ---

    async def notify(self, event):
        await self.send_json(event["message"])

    async def revoke(self, event):
        """Huquq o'zgardi / foydalanuvchi o'chirildi: xabar + 4403.

        (frontend yangi guruhlar bilan qayta ulanadi)
        """
        await self.send_json(event["message"])
        await self.close(code=CLOSE_FORBIDDEN)
