# Sevento — backend

Savdo, ombor, nasiya va kassa hisobi tizimi (ko'p nuqtali). Backend: Django 5.2 + DRF + Channels + Celery, PostgreSQL, Redis.

Frontend alohida repoda: [sevento_front](https://github.com/shaxobiddindev/sevento_front). Ikkalasi faqat REST (`/api/v1/`) va WebSocket (`/ws/v1/`, 2-bosqichdan) orqali gaplashadi.

## Holat

Barcha rejalashtirilgan bosqichlar (0–10) tugagan — batafsil: [docs/roadmap.md](docs/roadmap.md).

| Bosqich | Holat |
|---|---|
| 0. Reja | ✅ `docs/` |
| 1. Skelet, Docker, JWT (cookie refresh), rollar, nuqtalar, audit, hodisalar | ✅ |
| 2. Realtime asosi (Channels, ticket, guruhlar, `session.revoked`, `system.notice`) | ✅ |
| 3. Katalog, valyuta kursi (CBU adapteri, Celery Beat) | ✅ |
| 4. Kirim, partiya (FIFO), tannarx taqsimlash, ombor harakatlari, `stock.changed` | ✅ |
| 5. Naqd savdo (POS), FIFO chiqim, aralash valyuta va qaytim, chek PDF, kassa qoldig'i | ✅ |
| 6. Nasiya, mijozlar, kredit limiti, qarz to'lovi, mijoz hisobi, kassa smenasi, muddati o'tgan qarz | ✅ |
| 7. Ko'chirish, inventarizatsiya, hisobdan chiqarish, savdo qaytarish | ✅ |
| 8. Hisobotlar (13 ta, PDF/Excel, fonda tayyorlash), rahbar dashboardi (jonli) | ✅ |
| 9. PWA va Tauri desktop uchun moslashuv (WS originlari) | ✅ |
| 10. Test qamrovi (≥95%, CI chegarasi), OpenAPI tekshiruvi, demo ma'lumotlar, e2e, hujjatlar | ✅ |

## Hujjatlar

| Hujjat | Mazmuni |
|---|---|
| [docs/architecture.md](docs/architecture.md) | diagramma, papka tuzilishi, qatlamlar, modullar chegarasi, strategiya/adapter joylari, API va JWT qoidalari, sozlamalar |
| [docs/er-diagram.md](docs/er-diagram.md) | ER-diagramma (Mermaid) |
| [docs/domain-events.md](docs/domain-events.md) | hodisalar mexanizmi va ro'yxati |
| [docs/realtime.md](docs/realtime.md) | WebSocket: ticket, guruhlar, xabar turlari |
| [docs/permissions.md](docs/permissions.md) | huquqlar, rollar, nuqta chegarasi |
| [docs/api/openapi.yaml](docs/api/openapi.yaml) | OpenAPI 3 sxema (frontend turlari shundan generatsiya qilinadi) |

## Ishga tushirish (Docker)

```bash
git clone https://github.com/shaxobiddindev/sevento_back
git clone https://github.com/shaxobiddindev/sevento_front   # yonma-yon papkada
cd sevento_back
cp .env.example .env        # DJANGO_SECRET_KEY, BOOTSTRAP_ADMIN_*, POSTGRES_PASSWORD ni o'zgartiring
docker compose up --build
```

- Frontend: http://localhost:3000/ (Nginx `/api` va `/ws` ni backend ga proxy qiladi; PWA sifatida o'rnatiladi)
- API hujjati (Swagger): http://localhost:8000/api/v1/docs/
- Admin panel: http://localhost:8000/admin/
- Konteyner ishga tushganda: migratsiya → `bootstrap` (tizim rollari, davriy vazifalar, MB bo'sh bo'lsa `.env` dagi `BOOTSTRAP_ADMIN_*` bo'yicha rahbar).
- Xizmatlar: `backend` (uvicorn, ASGI — REST + WebSocket), `celery_worker` (fon vazifalari, hisobot fayllari), `celery_beat` (jadval MB da), `frontend` (Nginx), `postgres`, `redis`.

### Demo ma'lumotlar

```bash
DEMO_PASSWORD=... python manage.py seed_demo     # yoki .env da SEED_DEMO=1 (konteyner ishga tushganda)
```

3 nuqta (2 do'kon, ombor), har rol uchun foydalanuvchi (`demo_buxgalter`, `demo_omborchi`, `demo_sotuvchi1`, `demo_sotuvchi2`), katalog va narxlar, kirim, ko'chirish, naqd/karta va nasiya savdolar, qarz to'lovi, hisobdan chiqarish. Hammasi app servislari orqali yoziladi (qoldiq, tannarx, hodisalar, audit — haqiqiy oqim bilan bir xil). Idempotent; mavjud ma'lumot bilan to'qnashsa hech narsa yozmasdan to'xtaydi. Parol berilmasa tasodifiy yaratilib bir marta ko'rsatiladi.

### Ishlab chiqarish (prod) uchun

- `DJANGO_SETTINGS_MODULE=config.settings.prod`: `DEBUG=False`, HTTPS redirect, HSTS, refresh cookie doim `Secure`.
- Sirlar faqat muhitdan (`.env`/orkestrator): `DJANGO_SECRET_KEY`, `DATABASE_URL`, `POSTGRES_PASSWORD`, `BOOTSTRAP_ADMIN_PASSWORD`.
- `DJANGO_ALLOWED_HOSTS`, `DJANGO_TRUSTED_ORIGINS` (brauzer manzillari) — aniq qiymatlar; WebSocket originlari default bo'yicha `DJANGO_TRUSTED_ORIGINS` + Tauri (`REALTIME_ALLOWED_ORIGINS` bilan o'zgartiriladi).
- TLS — tashqi Nginx/balanser da; ichki Nginx `X-Forwarded-Proto` ni uzatadi.

## Lokal ishlab chiqish

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements/dev.txt
cp .env.example .env                       # DATABASE_URL va REDIS_URL lokal manzilga
python manage.py migrate
python manage.py bootstrap
uvicorn config.asgi:application --reload   # http://localhost:8000
celery -A config worker -l info            # alohida terminalda
celery -A config beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

Chek PDF (WeasyPrint) uchun tizimda Pango va o'zbek harflari bor shrift kerak: Debian/Ubuntu da `sudo apt install libpango-1.0-0 libpangoft2-1.0-0 fonts-dejavu-core` (Docker image da bor).

Frontend dev serveri (`npm run dev`, 5173-port) `/api` ni 8000 ga proxy qiladi — bitta origin, cookie `SameSite=Strict` bilan ishlaydi.

## Tekshiruvlar

```bash
ruff check . && ruff format --check .     # lint
lint-imports                              # modul chegaralari (pyproject.toml dagi 16 kontrakt)
pytest --cov                              # testlar + qamrov (≥95%; PostgreSQL + Redis kerak)
DJANGO_SETTINGS_MODULE=config.settings.test python manage.py spectacular --file docs/api/openapi.yaml --validate --fail-on-warn
python manage.py makemigrations --check --dry-run
```

CI (`.github/workflows/ci.yml`) shularni, qamrov chegarasini va `docs/api/openapi.yaml` yangiligini tekshiradi. Sxema sifati testlari (`core/tests/test_openapi.py`): har operatsiya tegli, 2xx javoblar tavsiflangan (frontend turlari `unknown` bo'lmasin).
Brauzer e2e testlari (Playwright, 9 ta oqim + yangi versiya) va desktop e2e — frontend repoda (`npm run e2e`, `e2e.yml`). Sinov muhitida `THROTTLE_LOGIN=1000/min` qo'ying.

## API qisqacha

- Hamma narsa `/api/v1/` ostida; xato formati, pagination va filtrlar — [architecture.md §7](docs/architecture.md#7-api-qoidalari).
- Kirish: `POST /api/v1/auth/login/` → `{access, user}` + httpOnly refresh cookie (`SameSite=Strict`, faqat `/api/v1/auth/` yo'liga).
  `POST /api/v1/auth/refresh/` (cookie) → yangi access, refresh aylantiriladi; `POST /api/v1/auth/logout/` qora ro'yxat.
  Access token ~15 daqiqa, `Authorization: Bearer ...`.
- `GET /api/v1/auth/me/` — foydalanuvchi, rol, huquqlar ro'yxati, nuqtalar (frontend menyu va guard shu asosida).
- Huquqlar: har endpointda `HasCapability` + nuqta chegarasi ([permissions.md](docs/permissions.md)).
- Muhim `POST` lar `Idempotency-Key` sarlavhasini qo'llaydi (takroriy so'rov ikkinchi hujjat yaratmaydi).
- Valyuta: `GET /api/v1/currency-rates/latest/` (joriy kurslar), `POST /api/v1/currency-rates/` (qo'lda), `POST /api/v1/currency-rates/fetch/` (manbadan hozir). Kunlik avtomatik yangilash — Celery Beat vazifasi `currency: kursni yangilash` (vaqti admin paneldagi *Periodic tasks* da, MB da). Manba — sozlama `currency.rate_provider` (`cbu` / `manual`), URL — `CURRENCY_CBU_URL`.
- Katalog: `/api/v1/catalog/{categories,units,price-types,products}/`; `GET products/?branch=<id>` joriy narxlarni shu nuqtaga xos narxlar bilan qaytaradi; `POST products/<id>/set-price/` yangi narx (tarix saqlanadi).
- Kirim: `/api/v1/purchasing/{suppliers,expense-types,purchases}/`; `GET purchases/<id>/preview/` — joriy kurs bilan tannarx oldindan hisobi, `POST purchases/<id>/receive/` (`Idempotency-Key`) — qabul (partiyalar yaratiladi, kurs qotiriladi), `POST purchases/<id>/cancel/ {reason}` — bekor qilish (partiyalardan chiqim bo'lmagan bo'lsa).
- Ombor: `GET /api/v1/inventory/stock/` (qoldiq, `?below_minimum=true`, `?category=`, `?search=`; `PATCH stock/<id>/ {min_quantity}` — `inventory.manage`), `GET inventory/movements/` (harakatlar jurnali), `GET inventory/batches/` (partiyalar, `inventory.view_cost`). Tannarx maydonlari `inventory.view_cost` huquqisiz `null`.
- Savdo: `POST /api/v1/sales/` (`Idempotency-Key`) — bitta so'rovda yakunlangan savdo: `items` (tovar, miqdor, chegirma), `payments` (to'lov turi, valyuta, summa), `expected_total`; narxni server belgilaydi. `GET sales/pos-products/` — kassa qidiruvi (narx + qoldiq, `?barcode=`, `?ids=`), `GET sales/pos-config/`, `GET sales/<id>/receipt/` — chek PDF, `POST sales/<id>/cancel/` (`sales.cancel`), `GET sales/summary/` — kunlik xulosa.
- To'lov va kassa: `/api/v1/payments/methods/` (ro'yxat — kassir ham, o'zgartirish — `settings.manage`), `payments/cashboxes/` (qoldiq), `payments/cash-transactions/` (jurnal), `payments/cash-categories/`.
- Nasiya: `POST /api/v1/sales/` ga `customer` (+ `due_date`) — to'lov jamidan kam bo'lsa qolgani qarz (limitdan oshsa 409 `credit_limit_exceeded`). Mijozlar: `/api/v1/payments/customers/` (karta: kredit holati, ochiq qarzlar), `POST customers/<id>/pay/` (`Idempotency-Key`) — qarz to'lovi, `GET customers/<id>/payoff/?currency=` — to'liq yopish summasi, `GET customers/<id>/ledger/` — akt-sverka. Qarzlar: `payments/debts/` (`?overdue=true`), to'lovlar jurnali: `payments/payments/` (`POST <id>/refund/`).
- Kassa smenasi: `GET payments/shifts/current/?branch=`, `POST payments/shifts/open/`, `POST payments/shifts/<id>/close/ {actual: [{currency, amount}]}`; qo'lda yozuv: `POST payments/cash-transactions/`. Muddati o'tgan qarzlar — Celery Beat `payments: muddati o'tgan qarzlar` (08:05).
- WebSocket `/ws/v1/`: `POST /api/v1/realtime/ticket/` → 30 s lik bir martalik ticket → ulanishdan keyin birinchi xabar `{"type":"auth","payload":{"ticket"}}` → `auth.ok`. Xabar formati `{type, payload, timestamp}`, turlar ro'yxati — [realtime.md](docs/realtime.md).
- Ombor hujjatlari: `inventory/transfers/` (`send`, `receive`, `cancel`, `destinations`), `inventory/counts/` (`items`, `complete`, `cancel`), `inventory/write-offs/`, `inventory/write-off-reasons/`. Qaytarish: `POST /api/v1/sales/returns/` (`Idempotency-Key`), `GET sales/returns/`.
- Hisobotlar: `GET /api/v1/reports/` (foydalanuvchiga ochiq hisobotlar va filtrlar ta'rifi), `GET reports/<key>/?...` (jadval, JSON), `POST reports/<key>/export/ {format: pdf|xlsx, params}` → fayl (200) yoki fon vazifasi (202, tayyor bo'lsa `report.ready`), `GET reports/jobs/` va `reports/jobs/<id>/download/`, `GET reports/dashboard/?period=today|7d|30d|month&branch=`. Yangi hisobot — `apps/reports/definitions/` ga bitta fayl (mavjud kod o'zgarmaydi).

