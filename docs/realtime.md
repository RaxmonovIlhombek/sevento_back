# Real vaqt (WebSocket)

> Holat: 2-bosqich amalga oshirildi — `apps/realtime` (consumer, ticket, guruhlar, router, notice API)
> va frontend `shared/realtime` (RealtimeClient, invalidate xaritasi, indikator, polling).
> Keyingi bosqichlar faqat `router.route(...)` qatorlari va `invalidationRules` yozuvlarini qo'shadi.
>
> Kod joylari: backend `apps/realtime/{consumers,tickets,router,subscribers}.py`,
> `config/asgi.py` (OriginValidator, `REALTIME_ALLOWED_ORIGINS`); frontend
> `src/shared/realtime/{client,invalidation,store,api}.ts`, `src/app/providers/RealtimeProvider.tsx`.

## 1. Prinsip

WebSocket — **faqat bildirishnoma kanali**. Ma'lumot manbai doimo REST + PostgreSQL.
Xabar kelganda frontend tegishli TanStack Query keshini `invalidate` qiladi va REST dan qayta o'qiydi.
Ulanish uzilsa tizim ishlashda davom etadi (faqat jonli yangilanish to'xtaydi, polling yoqiladi).

## 2. Ulanish va autentifikatsiya

```mermaid
sequenceDiagram
  autonumber
  participant F as Frontend
  participant R as REST /api/v1/realtime/ticket/
  participant WS as /ws/v1/
  participant RD as Redis

  F->>R: POST (Authorization: Bearer access)
  R->>RD: SETEX ws:ticket:{random} 30s {user_id}
  R-->>F: 201 {"ticket": "...", "expires_in": 30}
  F->>WS: ulanish (URL da hech qanday token/ticket yo'q)
  WS-->>F: accept
  Note over WS: 5 soniya ichida auth kelmasa → close 4408
  F->>WS: {"type":"auth","payload":{"ticket":"..."}}
  WS->>RD: GETDEL ws:ticket:{...}  (bir martalik)
  alt ticket yo'q / eskirgan
    WS-->>F: {"type":"auth.error", ...} + close 4401
  else foydalanuvchi faol emas
    WS-->>F: close 4403
  else OK
    WS->>WS: foydalanuvchi guruhlarini hisoblash, group_add
    WS-->>F: {"type":"auth.ok","payload":{"user_id":7,"groups":["user_7","role_seller","branch_3"]}}
  end
  loop har 25 soniya
    F->>WS: {"type":"ping"}
    WS-->>F: {"type":"pong"}
  end
```

- Ticket: 32 bayt `secrets.token_urlsafe`, Redis da 30 soniya, **bir marta** ishlatiladi (`GETDEL` atomar), foydalanuvchi id ga bog'langan.
- Ticket URL ga ham, sarlavhaga ham yozilmaydi — birinchi xabarda keladi. Shuning uchun loglarda/proxy tarixida qolmaydi.
- Auth dan oldin kelgan boshqa har qanday xabar → close 4401.
- Bir foydalanuvchi bir nechta ulanish ochishi mumkin (ikki tab, telefon + kompyuter).
- Foydalanuvchi o'chirilsa (`user.deactivated`) yoki roli/nuqtasi o'zgarsa (`user.updated`) → `user_{id}` guruhiga `session.revoked` yuboriladi va server ulanishni 4403 bilan yopadi; frontend qayta ticket oladi (yangi huquqlar bilan) yoki login sahifasiga o'tadi.
- Access token eskirishi WS ga ta'sir qilmaydi (ulanish ticket paytida tekshirilgan); uzoq ulanishlar uchun server har 15 daqiqada foydalanuvchi hali faolligini tekshiradi.

### Yopish kodlari

| Kod | Ma'nosi | Frontend harakati |
|---|---|---|
| 1000 | oddiy yopish (logout) | qayta ulanmaydi |
| 1001 / 1006 | server qayta ishga tushdi, tarmoq uzildi | backoff bilan qayta ulanadi |
| 4401 | autentifikatsiya yo'q / ticket yaroqsiz | yangi ticket olib qayta ulanadi; REST ham 401 bersa → login |
| 4403 | ruxsat yo'q / foydalanuvchi faol emas | `me` ni qayta o'qiydi, kerak bo'lsa login |
| 4408 | auth kutish vaqti tugadi | darhol qayta ulanadi |
| 4429 | juda ko'p ulanish (bitta userga > 10) | 30 soniyadan keyin |

## 3. Guruhlar (rooms)

Guruhlarga a'zolikni **server** hal qiladi, mijoz "obuna bo'laman" deb so'ramaydi — shu bilan huquqsiz obuna imkonsiz.

| Guruh | Kim a'zo | Nima keladi |
|---|---|---|
| `user_{id}` | shu foydalanuvchi (barcha ulanishlari) | `report.ready`, `session.revoked` (o'chirildi, rol/nuqta/parol o'zgardi), shaxsiy bildirishnomalar |
| `role_{code}` | shu roldagi hamma (`role_owner`, `role_accountant`, `role_storekeeper`, `role_seller`) | rolga qaratilgan: `payment.received` (buxgalter), `debt.overdue`, `dashboard.updated` (rahbar); rol huquqlari o'zgarsa `session.revoked` |
| `branch_{id}` | `UserBranch` orqali shu nuqtaga biriktirilganlar; `branches.view_all` huquqi borlar **barcha** faol nuqtalarga | `stock.changed`, `stock.below_minimum`, `transfer.*` |
| `broadcast` | hamma autentifikatsiyadan o'tganlar | `currency.rate_updated`, `system.notice` |

Guruhlar `auth` paytida `accounts.selectors` orqali hisoblanadi (`get_realtime_groups(user)`), ro'yxat `auth.ok` da qaytariladi (debug uchun qulay).

## 4. Xabar formati

Barcha xabarlar (ikkala yo'nalishda) bir xil konvert:

```json
{
  "type": "stock.changed",
  "payload": { "...": "..." },
  "timestamp": "2026-10-22T14:03:11.512+05:00"
}
```

- `type` — hodisa nomi bilan bir xil (`<aggregat>.<fe'l>`), kichik harf.
- `payload` — faqat identifikatorlar va ekranni yangilash uchun yetarli minimal maydonlar. To'liq ma'lumot REST dan olinadi.
- `timestamp` — server vaqti, ISO 8601, `Asia/Tashkent`.
- Sezgir maydonlar (tannarx, foyda) WS payload ida **yo'q**: `branch_{id}` guruhida sotuvchi ham bor.

## 5. Xabar turlari

### Mijoz → server

| `type` | `payload` | Izoh |
|---|---|---|
| `auth` | `{ticket}` | ulanishdan keyin 5 s ichida, bir marta |
| `ping` | `{}` | har 25 s; 2 ta `pong` kelmasa mijoz ulanishni qayta ochadi |

Boshqa hech qanday mijoz xabari qabul qilinmaydi (noma'lum `type` → e'tiborsiz, log).

### Server → mijoz

| `type` | Guruh | `payload` | Frontend: qaysi kesh invalidate | Bosqich |
|---|---|---|---|---|
| `auth.ok` | ulanish | `{user_id, groups: []}` | — | 2 |
| `auth.error` | ulanish | `{code, message}` | — (keyin close) | 2 |
| `pong` | ulanish | `{}` | — | 2 |
| `session.revoked` | `user_{id}` / `role_{code}` | `{reason: "deactivated" \| "permissions_changed" \| "password_changed"}` — keyin server 4403 bilan yopadi | `deactivated` → logout; aks holda `me` qayta o'qiladi, yangi ticket bilan qayta ulanadi | 2 ✅ |
| `system.notice` | `broadcast` | `{level: "info" \| "warning" \| "error", message}` (`POST /api/v1/realtime/notice/`, `settings.manage`) | — (toast) | 2 ✅ |
| `currency.rate_updated` | `broadcast` | `{rates: [{currency, rate, date}], source}` | `['currency']`, `['products']` + toast "USD = 12 650,45 so'm" | 3 ✅ |
| `stock.changed` | `branch_{id}` | `{branch_id, product_id, quantity, delta, movement_type, document: {type, id, number}}` — tannarx yo'q | `['inventory']` (qoldiq, harakatlar, partiyalar; debounce 1,5 s) | 4 ✅ (kirim), 5 (savdo) |
| `stock.below_minimum` | `branch_{id}` (omborchi, sotuvchi; rahbar `branches.view_all` orqali barcha nuqtalar guruhida) | `{branch_id, product_id, product_name, quantity, min_quantity, unit}` | `['inventory']` + ogohlantirish toast "Kam qoldi: …" | 4 ✅ |
| `dashboard.updated` | `role_owner` | `{branch_id, reason: "sale.completed" \| "sale.cancelled" \| "sale_return.completed" \| "payment.received"}` | `['dashboard']` (debounce 2 s) | 5, 8 |
| `payment.received` | `role_accountant`, `role_owner`, `branch_{id}` | `{payment_id, number, branch_id, customer_id, amount, currency, method, direction}` | `['payments']`, `['cashboxes', branch_id]`, `['customers', customer_id]`, `['debts']` | 6 |
| `payment.refunded` | xuddi shunday | `{payment_id, ...}` | xuddi shunday | 6 |
| `debt.overdue` | `role_accountant`, `role_owner` | `{debt_id, customer_id, customer_name, amount_remaining, currency, due_date, days_overdue}` | `['debts']`, `['customers', customer_id]` + ogohlantirish | 6 |
| `customer.credit_limit_warning` | `role_accountant`, `role_owner` | `{customer_id, customer_name, used_base, limit_base, percent}` | `['customers', customer_id]` + toast | 6 |
| `transfer.sent` | `branch_{to}` | `{transfer_id, number, from_branch_id, from_branch_name, to_branch_id, items_count}` | `['transfers']` + bildirishnoma (omborchi) | 7 |
| `transfer.received` | `branch_{from}`, `branch_{to}`, farq bo'lsa `role_owner` | `{transfer_id, number, from_branch_id, to_branch_id, has_discrepancy}` | `['transfers']`, `['stock', from]`, `['stock', to]` | 7 |
| `transfer.cancelled` | ikkala nuqta | `{transfer_id, number, reason}` | `['transfers']` | 7 |
| `report.ready` | `user_{id}` | `{job_id, report_key, format, download_url}` | `['reports','jobs']` + toast "yuklab olish" | 8 |
| `report.failed` | `user_{id}` | `{job_id, report_key, error}` | `['reports','jobs']` + xato toast | 8 |

Yangi tur qo'shilganda shu jadval yangilanadi; frontend da noma'lum `type` jim e'tiborsiz qoladi (eski mijoz yangi server bilan buzilmaydi).

## 6. Hodisadan xabargacha (backend)

```
domen hodisasi (on_commit) → realtime.subscribers → realtime.router (hodisa → guruhlar + payload qisqartirish)
→ channel_layer.group_send(group, {"type": "notify", "message": {...}})
→ RealtimeConsumer.notify() → self.send_json(message)
```

- `realtime.router` — oddiy jadval: `{"stock.changed": [to_branch_group], "payment.received": [role_accountant, role_owner, branch], ...}`. Yangi hodisa uchun bitta qator qo'shiladi.
- Celery ichidan chiqqan hodisalar (kurs, muddati o'tgan qarz) ham xuddi shu yo'ldan o'tadi (`channel_layer` Redis orqali, worker dan ham ishlaydi).
- `group_send` `transaction.on_commit` ichida bo'lgani uchun MB ga yozilmagan narsa haqida xabar ketmaydi.

## 7. Frontend tomoni

- Bitta `RealtimeClient` (singleton), `RealtimeProvider` ichida; login dan keyin ochiladi, logout da 1000 bilan yopiladi.
- **Qayta ulanish:** eksponensial backoff `1s, 2s, 4s, ... 30s` + tasodifiy jitter; har urinishda **yangi ticket** olinadi (REST 401 bersa avval refresh).
  Brauzer `online` hodisasi va tab yana ko'ringanda (`visibilitychange`) darhol qayta ulanish.
- **Holat indikatori:** `connecting | online | offline` — sarlavhada kichik nuqta; `offline` 10 s dan oshsa "Jonli yangilanish uzildi, ma'lumotlar vaqti-vaqti bilan yangilanadi" banneri.
- **Polling ga qaytish:** `offline` holatida muhim so'rovlar (`stock`, `dashboard`, `transfers`, `debts`) uchun TanStack `refetchInterval: 30_000` yoqiladi; `online` bo'lganda o'chiriladi va bir marta hammasi invalidate qilinadi (uzilgan vaqtda o'tkazib yuborilgan o'zgarishlar uchun).
- **Invalidate xaritasi** — `shared/realtime/invalidation.ts` da `type → queryKey[]` jadvali (yuqoridagi ustun). Xabar ishlovchilari komponent ichida emas, shu bitta joyda.
- Tez-tez keladigan `stock.changed` / `dashboard.updated` uchun 1–2 s debounce (bir vaqtda 20 ta sotuv → 1 ta qayta o'qish).

## 8. Testlar

Backend (`apps/realtime/tests/`, `WebsocketCommunicator`, ✅):
- ticket siz ulanib `auth` yubormaslik → 4408; auth dan oldin boshqa xabar → 4401; yaroqsiz ticket → `auth.error` + 4401; ticketni ikki marta ishlatish → ikkinchisi 4401; faol bo'lmagan foydalanuvchi → 4403.
- sotuvchi `branch_1` da bo'lsa `branch_2` xabarini **olmaydi**; rahbar ikkalasini oladi.
- hodisa tranzaksiya commit bo'lgandan keyin keladi; rollback bo'lsa kelmaydi.
- `user.deactivated` → `session.revoked` + 4403 (boshqalarga ta'sir yo'q); rol huquqi o'zgarsa `role_{code}` guruhi; ism o'zgarsa jim.
- ulanish limiti (4429) va yopilgach hisob kamayishi; `POST /realtime/notice/` → `broadcast`.
- `currency.rate_updated` (kurs kiritilganda) `broadcast` orqali boshqa foydalanuvchiga yetib keladi (3 ✅, `apps/currency/tests/test_realtime.py`).
- `stock.changed` faqat shu nuqta guruhiga ketadi, payloadda tannarx yo'q (4 ✅, `apps/inventory/tests/test_realtime.py`).
- Keyingi bosqichlar: `stock.changed` savdodan keyin (5).

Frontend (`src/shared/realtime/*.test.ts`, soxta WebSocket + fake timers, ✅):
- ticket → `auth` birinchi xabar → `auth.ok` → online; `pong` uzatilmaydi; buzuq JSON e'tiborsiz.
- uzilganda backoff (eksponensial, chegarali, jitter) bilan **yangi ticket** olib qayta ulanadi; `auth.ok` dan keyin backoff nolga qaytadi.
- 4401/4408/4403 → kutmasdan; ticket olib bo'lmasa offline + keyinroq.
- ping har 25 s; 2 ta pong kelmasa yopib qayta ochadi; `close()` → 1000, qayta ulanmaydi.
- invalidate xaritasi: noma'lum tur jim; debounce li turlar bir xil kalitlarni yig'adi.

Brauzerda (Playwright, qo'lda): ikki oyna — rahbar `system.notice` yuboradi → sotuvchida darhol toast; rolni o'zgartirish → sotuvchida `me` yangilanadi va qayta ulanadi; o'chirish → sotuvchi login sahifasiga chiqariladi.
