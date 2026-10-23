# Domen hodisalari

> Holat: mexanizm va accounts/branches/core hodisalari 1-bosqichda amalga oshirildi; qolgan jadvallar reja.

## 1. Mexanizm

```mermaid
sequenceDiagram
  autonumber
  participant S as sales.services.complete_sale()
  participant DB as PostgreSQL
  participant EV as core.events
  participant D as dispatcher (on_commit)
  participant AU as audit.subscribers
  participant RT as realtime.subscribers
  participant R as Redis channel layer

  S->>DB: BEGIN
  S->>DB: Sale, SaleItem, StockMovement ... yozish
  S->>EV: publish(SaleCompleted(...))
  EV->>DB: OutboxEvent(status=pending) — shu tranzaksiyada
  EV->>D: transaction.on_commit(dispatch, event_id)
  S->>DB: COMMIT
  Note over D: faqat commit muvaffaqiyatli bo'lsa ishlaydi
  D->>AU: handle(event)  → AuditLog
  D->>RT: handle(event)  → group_send(...)
  RT->>R: branch_3, role_owner ...
  D->>DB: OutboxEvent(status=dispatched)
```

- `core.events.publish(event)` **faqat** `transaction.atomic` ichidan chaqiriladi (tashqarida chaqirilsa xato).
- Hodisa avval `core.OutboxEvent` jadvaliga yoziladi (shu tranzaksiyada), keyin `transaction.on_commit` ichida obunachilarga tarqatiladi.
  Rollback bo'lsa — outbox yozuvi ham, hodisa ham bo'lmaydi. Commit dan keyin jarayon o'lib qolsa — `core.tasks.redispatch_outbox` (Celery, har daqiqa) `pending` yozuvlarni qayta tarqatadi.
- Obunachi `@subscribe("sale.completed")` dekoratori bilan ro'yxatga olinadi, har app ning `subscribers.py` fayli `AppConfig.ready()` da yuklanadi.
- Obunachi xatosi boshqa obunachilarga va asosiy so'rovga ta'sir qilmaydi: log + outbox da `attempts` oshadi.
- Og'ir ish (PDF, email, tashqi API) obunachida bajarilmaydi — obunachi Celery vazifasini chaqiradi.
- Hodisa ob'ekti — `frozen dataclass`, payload JSON ga aylantiriladi (Decimal → satr, datetime → ISO).

```python
@dataclass(frozen=True, kw_only=True)
class Event:
    name: ClassVar[str]
    occurred_at: datetime
    actor_id: int | None
    branch_id: int | None
    aggregate_type: str
    aggregate_id: int

@dataclass(frozen=True, kw_only=True)
class SaleCompleted(Event):
    name = "sale.completed"
    sale_id: int
    number: str
    customer_id: int | None
    total: Decimal
    currency: str
    total_base: Decimal
    debt_amount: Decimal
    items: list[dict]   # [{product_id, quantity, unit_price, cost_base}]
```

Nomlash: `<aggregat>.<o'tgan zamon fe'l>`, kichik harf, nuqta bilan.

## 2. Hodisalar ro'yxati

Ustunlar: **Audit** — audit jurnaliga yoziladimi; **WS** — WebSocket ga chiqadimi (guruhlar [realtime.md](realtime.md) da); **Boshqa** — boshqa obunachilar.

### accounts

| Hodisa | Qachon | Payload | Audit | WS | Boshqa |
|---|---|---|---|---|---|
| `user.logged_in` | muvaffaqiyatli login | user_id, ip, user_agent | ✔ | — | — |
| `user.login_failed` | noto'g'ri parol | username, ip | ✔ | — | throttle hisoblagichi |
| `user.created` / `user.updated` / `user.deactivated` | admin amali | user_id, username, changes {maydon: {old, new}} | ✔ | — | `user.deactivated` → realtime shu user sessiyalarini yopadi (2-bosqich) |
| `user.password_changed` | o'zi yoki admin parolni almashtirdi | user_id, by_self | ✔ | — | |
| `role.created` / `role.updated` / `role.deleted` | rol boshqaruvi | role_id, code, capabilities / changes | ✔ | — | |
| `setting.changed` (core) | tizim sozlamasi o'zgardi | key, old_value, new_value | ✔ | — | kesh tozalanadi |
| `system.notice` (realtime) | rahbar hammaga xabar yubordi | level, message | ✔ | ✔ `broadcast` | |

### branches / catalog / currency

| Hodisa | Qachon | Payload | Audit | WS | Boshqa |
|---|---|---|---|---|---|
| `branch.created` / `branch.updated` | | branch_id, code, branch_name, type / changes | ✔ | — | |
| `category.created` / `category.updated` | | category_id, category_name, parent_id / changes | ✔ | — | |
| `unit.saved` / `price_type.saved` | ma'lumotnoma yaratildi/o'zgardi | id, code, changes | ✔ | — | |
| `product.created` / `product.updated` | | product_id, sku, product_name / changes {maydon: {old, new}} | ✔ | — | |
| `product.price_changed` | yangi narx qatori | product_id, price_type, currency, old_amount, new_amount; branch_id (meta) | ✔ | — | |
| `currency.created` / `currency.updated` | valyuta jadvali o'zgardi | currency_id, code / changes | ✔ | — | |
| `currency.rate_updated` | Celery (`currency.fetch_rates`) yoki qo'lda kiritildi | rates: [{currency, rate, date}], source (`cbu` / `manual`) | ✔ | ✔ `broadcast` | frontend: valyuta va tovar keshlari + toast |

### purchasing

| Hodisa | Qachon | Payload | Audit | WS | Boshqa |
|---|---|---|---|---|---|
| `supplier.saved` | yetkazib beruvchi yaratildi/o'zgardi | supplier_id, supplier_name, created, changes | ✔ | — | 4 ✅ |
| `expense_type.saved` | xarajat turi yaratildi/o'zgardi | expense_type_id, code, changes | ✔ | — | 4 ✅ |
| `purchase.created` | kirim qoralamasi yaratildi | purchase_id, number, supplier_id; branch_id (meta) | ✔ | — | 4 ✅ |
| `purchase.received` | kirim tasdiqlandi (tovar omborga kirdi) | purchase_id, number, supplier_id, currency, rate_to_base, subtotal, expenses_total_base, total_base, items [{product_id, quantity, landed_unit_cost_base}]; branch_id (meta) | ✔ | — | 4 ✅. **inventory** emas! kirim service i `inventory.services.receive_stock()` ni to'g'ridan-to'g'ri chaqiradi (bir tranzaksiyada bo'lishi shart), hodisa faqat xabar uchun |
| `purchase.cancelled` | qoralama yoki tasdiqlangan kirim bekor qilindi | purchase_id, number, previous_status, reason | ✔ | — | 4 ✅ |

### inventory

| Hodisa | Qachon | Payload | Audit | WS | Boshqa |
|---|---|---|---|---|---|
| `stock.changed` | har qanday qoldiq o'zgarishi (kirim, kirim bekor qilish; keyin savdo, qaytarish, ko'chirish, inventarizatsiya, hisobdan chiqarish) | branch_id, product_id, quantity_before, quantity_after, delta, movement_type, document_type, document_id, document_number | — (`audit=False`: harakat jurnali o'zi tarix) | ✔ `branch_{id}` (tannarxsiz) | 4 ✅ (kirim); `stock.below_minimum` tekshiruvi shu joyda |
| `stock.below_minimum` | qoldiq kamayib minimaldan **pastga o'tganda** (har chiqimda emas: `StockLevel.below_minimum` bayrog'i bilan) | branch_id, product_id, product_name, quantity, min_quantity, unit | ✔ | ✔ `branch_{id}` | 4 ✅. Minimal: nuqta bo'yicha → tovar → sozlama `inventory.default_min_quantity` |
| `stock.min_quantity_changed` | nuqta bo'yicha minimal qoldiq o'zgartirildi | product_id, old_value, new_value; branch_id (meta) | ✔ | — | 4 ✅ |
| `transfer.created` | ko'chirish qoralamasi yaratildi | transfer_id, number, from_branch_id, to_branch_id; branch_id (meta) = jo'natuvchi | ✔ | — | 7 ✅ |
| `transfer.sent` | jo'natildi (manbadan FIFO chiqim) | transfer_id, number, from/to_branch_id, from/to_branch_name, items_count, total_cost_base | ✔ | ✔ `branch_{from}` va `branch_{to}` — **bitta xabar** (id bilan, ikkala guruhdagi foydalanuvchiga bir marta); payload tannarxsiz | 7 ✅. Qabul qiluvchi omborchiga toast |
| `transfer.received` | qabul qilindi (qisman farq bilan ham) | transfer_id, number, from/to_branch_*, has_discrepancy, shortage_cost_base, discrepancies [{product_id, product_name, quantity, quantity_received}]; branch_id (meta) = qabul qiluvchi | ✔ | ✔ ikkala nuqta; farq bo'lsa `dashboard.view` huquqi borlarning `user_{id}` lari ham (o'sha xabar) | 7 ✅. Kam kelgan qism avtomatik `write_off` (sabab `transfer_shortage`) |
| `transfer.cancelled` | qoralama yoki jo'natilgani bekor qilindi | transfer_id, number, from/to_branch_*, previous_status, reason | ✔ | ✔ jo'natilgan bo'lsa ikkala nuqta, qoralama — faqat `branch_{from}` | 7 ✅. Jo'natilgani — tovar manbadagi asl partiyalarga |
| `stock_count.created` | inventarizatsiya ochildi | count_id, number, items_count | ✔ | — | 7 ✅ |
| `stock_count.completed` | yakunlandi, farqlar qo'llandi | count_id, number, items_counted, surplus_items, shortage_items, surplus_cost_base, shortage_cost_base | ✔ | — (qoldiq `stock.changed` bilan) | 7 ✅ |
| `stock_count.cancelled` | yakunlanmagan inventarizatsiya bekor qilindi | count_id, number | ✔ | — | 7 ✅ |
| `write_off_reason.saved` | sabab yaratildi/o'zgardi | reason_id, code, created, changes | ✔ | — | 7 ✅ |
| `write_off.completed` | hisobdan chiqarildi (yoki ko'chirish kamomadi) | write_off_id, number, reason, total_cost_base, items_count, transfer_id | ✔ | — (qoldiq `stock.changed` bilan) | 7 ✅ |
| `write_off.cancelled` | bekor qilindi — tovar asl partiyalarga | write_off_id, number, total_cost_base, reason | ✔ | — | 7 ✅. Ko'chirish kamomadi hujjati alohida bekor qilinmaydi |

### sales

| Hodisa | Qachon | Payload | Audit | WS | Boshqa |
|---|---|---|---|---|---|
| `sale.completed` | savdo yakunlandi | sale_id, number, seller_id, currency, total, total_base, cost_base, discount_total, items_count, payments [{method, currency, amount}], customer_id, debt_amount; branch_id (meta) | ✔ | ✔ `dashboard.updated` — `dashboard.view` huquqi borlarning `user_{id}` guruhlariga | 5–6 ✅ |
| `sale.cancelled` | yakunlangan savdo bekor qilindi (`sales.cancel`) | sale_id, number, total, currency, reason | ✔ | ✔ `dashboard.updated` | 5 ✅ |
| `sale_return.completed` | qaytarish yakunlandi (tovar omborga, summa qarzdan ayirildi va/yoki pul qaytarildi) | return_id, number, sale_id, sale_number, currency, total, total_base, cost_base, debt_reduction, refund_amount, items_count, customer_id, reason | ✔ | ✔ `branch_{id}` + `dashboard.updated` | 7 ✅ |

### payments

| Hodisa | Qachon | Payload | Audit | WS | Boshqa |
|---|---|---|---|---|---|
| `payment.received` | mijozdan to'lov qabul qilindi (savdo paytida va qarz to'lovi) | payment_id, number, method, currency, amount, amount_base, is_cash, cashbox_id, customer_id, allocated [{debt_id, amount, currency}], document_type, document_id, document_number; branch_id (meta) | ✔ | ✔ `branch_{id}` (buxgalter/rahbar `branches.view_all` orqali hamma nuqtada) + `dashboard.updated` | 5–6 ✅. Qarz to'lovida hodisa taqsimotdan keyin chiqadi. Qaytim alohida hodisa chiqarmaydi |
| `payment.refunded` | mijozga pul qaytarildi (savdo bekor qilinganda, qarz to'lovi qaytarilganda, tovar qaytarilganda — `original_payment_id` bo'sh) | payment_id, original_payment_id, number, method, currency, amount, is_cash, cashbox_id, customer_id, document_type, document_id, reason | ✔ | ✔ `branch_{id}` | 5–6 ✅ |
| `payment_method.saved` | to'lov turi yaratildi/o'zgardi | payment_method_id, code, created, changes | ✔ | — | 5 ✅ |
| `customer.saved` | mijoz yaratildi/o'zgardi | customer_id, customer_name, created, changes | ✔ | — | 6 ✅ |
| `debt.registered` | nasiya yozildi | debt_id, customer_id, amount, currency, due_date, document_type, document_id, document_number | ✔ | ✔ `debt.changed` → `branch_{id}` | 6 ✅ |
| `debt.settled` | qarz to'liq yopildi | debt_id, customer_id | ✔ | ✔ `debt.changed` | 6 ✅ |
| `debt.cancelled` | savdo bekor qilinib qarz bekor bo'ldi | debt_id, customer_id, amount, currency, reason | ✔ | ✔ `debt.changed` | 6 ✅ |
| `debt.reduced` | tovar qaytarilib qarz shu summaga kamaydi (`Debt.returned_amount`) | debt_id, customer_id, amount, currency, remaining, document_type, document_id, document_number | ✔ | ✔ `debt.changed` | 7 ✅. Qoldiq 0 bo'lsa `debt.settled` ham |
| `debt.overdue` | Celery (`payments.detect_overdue_debts`, default 08:05) muddati o'tganini aniqladi — har qarz uchun bir marta | debt_id, customer_id, customer_name, amount_remaining, currency, due_date, days_overdue | ✔ | ✔ `debts.manage` huquqi borlar (`user_{id}`) | 6 ✅ |
| `customer.credit_limit_warning` | qarz limitning N% (`payments.credit_limit_warning_percent`) chegarasidan o'tdi | customer_id, customer_name, used_base, limit_base, percent, base_currency | ✔ | ✔ `debts.manage` huquqi borlar | 6 ✅ |
| `cash_shift.opened` / `cash_shift.closed` | kassa smenasi ochildi / yopildi | shift_id, balances [{currency, opening, expected, actual, difference}] | ✔ | ✔ `cash.updated` → `branch_{id}` | 6 ✅ |
| `cash_entry.created` | kassaga qo'lda kirim/chiqim | transaction_id, cashbox_id, currency, direction, category, amount, note | ✔ | ✔ `cash.updated` | 6 ✅ |

### reports

| Hodisa | Qachon | Payload | Audit | WS | Boshqa |
|---|---|---|---|---|---|
| `report.exported` | hisobot fayli olindi (darhol yoki fonda tayyorlandi) | report_key, format, params, rows, job_id | ✔ | — | 8 ✅. Kim, qaysi hisobotni, qaysi filtrlar bilan |
| `report.ready` | Celery (`reports.generate_report`) faylni tayyorladi | user_id, job_id, report_key, title, format, download_url | — | ✔ faqat so'ragan `user_{id}` | 8 ✅ |
| `report.failed` | fondagi tayyorlash xato bilan tugadi | user_id, job_id, report_key, title, error | — | ✔ faqat so'ragan `user_{id}` | 8 ✅ |

Og'ir hisobot (`heavy = True`) yoki davri `reports.sync_max_days` (31) dan uzun bo'lsa — eksport `202` + `ReportJob`, aks holda fayl darhol qaytadi. Ko'rish (JSON) hodisa chiqarmaydi.

## 3. Hodisa ↔ WebSocket xabari

Hodisa nomi va WS xabar turi **bir xil** (`stock.changed` → `{type: "stock.changed"}`), faqat payload WS uchun qisqartiriladi (ichki id lar va narx-tannarx kabi sezgir maydonlar olib tashlanadi, masalan sotuvchi `cost_base` ni ko'rmaydi).
Istisno: `sale.completed`/`sale.cancelled`/`sale_return.completed` rahbar ekranida `dashboard.updated` bo'lib chiqadi (ichida nima o'zgargani emas, "dashboardni yangila" signali).

## 4. Audit jurnali

`audit.subscribers` barcha `Audit ✔` hodisalarga obuna bo'ladi va `AuditLog` ga yozadi:
`actor_id, branch_id, event_name, aggregate_type, aggregate_id, payload (JSON), ip, user_agent, request_id, created_at`.
`ip`/`user_agent`/`request_id` `core.context` (contextvars, middleware o'rnatadi) dan olinadi; Celery ichida bo'sh.
Audit jadvali faqat qo'shiladi (`INSERT`), o'zgartirish va o'chirish yo'q.
