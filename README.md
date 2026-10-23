# Sevento — backend

Savdo, ombor, nasiya va kassa hisobi tizimi (ko'p nuqtali). Backend: Django 5.2 + DRF + Channels + Celery, PostgreSQL, Redis.

Frontend alohida repoda: [sevento_front](https://github.com/shaxobiddindev/sevento_front). Ikkalasi faqat REST (`/api/v1/`) va WebSocket (`/ws/v1/`, 2-bosqichdan) orqali gaplashadi.

## Holat

| Bosqich | Holat |
|---|---|
| 0. Reja | ✅ `docs/` |
| 1. Skelet, Docker, JWT (cookie refresh), rollar, nuqtalar, audit, hodisalar | ✅ |
| 2. Realtime asosi (Channels, ticket, guruhlar, `session.revoked`, `system.notice`) | ✅ |
| 3. Katalog, valyuta kursi (CBU adapteri, Celery Beat) | ✅ |
| 4. Kirim, partiya (FIFO), tannarx taqsimlash, ombor harakatlari, `stock.changed` | ✅ |
| 5. Savdo (naqd), chek PDF, kassa qoldig'i | ⏳ keyingi |

Batafsil: [docs/roadmap.md](docs/roadmap.md).

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
cp .env.example .env        # DJANGO_SECRET_KEY va BOOTSTRAP_ADMIN_* ni o'zgartiring
docker compose up --build
```

- Frontend: http://localhost:3000/ (Nginx `/api` va `/ws` ni backend ga proxy qiladi)
- API hujjati (Swagger): http://localhost:8000/api/v1/docs/
- Admin panel: http://localhost:8000/admin/
- Birinchi ishga tushirishda `bootstrap` buyrug'i tizim rollarini, davriy vazifalarni va `.env` dagi `BOOTSTRAP_ADMIN_*` bo'yicha rahbarni yaratadi (MB da foydalanuvchi bo'lmasa).

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

Frontend dev serveri (`npm run dev`, 5173-port) `/api` ni 8000 ga proxy qiladi — bitta origin, cookie `SameSite=Strict` bilan ishlaydi.

## Tekshiruvlar

```bash
ruff check . && ruff format --check .     # lint
lint-imports                              # modul chegaralari (pyproject.toml dagi kontraktlar)
pytest                                    # testlar (PostgreSQL + Redis kerak, config/settings/test.py)
DJANGO_SETTINGS_MODULE=config.settings.test python manage.py spectacular --file docs/api/openapi.yaml --validate
```

CI (`.github/workflows/ci.yml`) shularni va `docs/api/openapi.yaml` yangiligini tekshiradi.

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
- WebSocket `/ws/v1/`: `POST /api/v1/realtime/ticket/` → 30 s lik bir martalik ticket → ulanishdan keyin birinchi xabar `{"type":"auth","payload":{"ticket"}}` → `auth.ok`. Xabar formati `{type, payload, timestamp}`, turlar ro'yxati — [realtime.md](docs/realtime.md).
