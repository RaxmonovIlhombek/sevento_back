# Ish rejasi (bosqichlar)

Har bosqich oxirida: kod ishlaydi (`docker compose up` bilan), testlar o'tadi, hujjatlar yangilangan, push qilingan. Tasdiqdan keyin keyingisi.

Frontend **har bosqichda backend bilan parallel** qilinadi (specdagi 9-bosqich tarqatiladi): bosqich oxirida ishlaydigan sahifalar bo'ladi, PWA va Tauri o'rami oxirida.

| # | Bosqich | Backend | Frontend | "Tayyor" mezoni |
|---|---|---|---|---|
| 0 | Reja | `docs/` (shu hujjatlar) | `docs/architecture.md` | tasdiq |
| 1 | Skelet va asos | loyiha tuzilishi, settings base/dev/prod/test, Docker (postgres, redis, backend, worker, beat), `core` (xato formati, pagination, events + outbox, SystemSetting, numbering, idempotency), `accounts` (JWT + httpOnly refresh cookie, rotation, blacklist, Role, capabilities, `me`), `branches`, `audit`, drf-spectacular, CI (ruff, import-linter, pytest) | Vite + React + TS skelet, Tailwind, router, i18n, API klient (refresh, 401/403, xato ko'rsatish), auth store (access xotirada), login, layout, nuqta tanlagich, foydalanuvchilar/nuqtalar CRUD, openapi-typescript generatsiya | login → me → logout ishlaydi; refresh aylanadi; audit yoziladi; testlar o'tadi |
| 2 | Realtime asosi | `realtime`: Channels + Redis, ticket endpoint, consumer, guruhlar, router, `session.revoked`, `system.notice`; Channels testlari | `RealtimeClient` (backoff, ticket, ping), holat indikatori, invalidate xaritasi, polling fallback | ikki brauzerda `system.notice` ko'rinadi; ruxsat testlari o'tadi |
| 3 | Katalog va valyuta | `catalog` (kategoriya, birlik, tovar, narx turi, narx tarixi), `currency` (valyuta, kurs, CBU adapteri, Celery Beat jadvali MB da), `currency.rate_updated` | katalog sahifalari (ro'yxat, forma, narxlar), valyuta va kurs sahifasi, kurs yangilanganda toast | kurs avtomatik tortiladi; tovar yaratish/narx |
| 4 | Kirim va tannarx | `purchasing` (yetkazib beruvchi, kirim, xarajatlar, taqsimlash strategiyalari), `inventory` asosi (StockLevel, Batch, StockMovement, `receive_stock`, costing registry + FIFO) | kirim sahifalari, tovar kartasi (partiyalar, harakatlar), qoldiq ro'yxati | kirim tasdiqlanganda partiya va tannarx to'g'ri; harakat jurnali |
| 5 | Savdo (naqd) | `sales` (savdo, FIFO chiqim, chek PDF), `payments` minimal (to'lov turi, naqd to'lov, kassa qoldig'i), `stock.changed`, `stock.below_minimum`, `dashboard.updated` | kassa (POS) sahifasi, chek chop etish, qoldiq jonli yangilanadi, min qoldiq ogohlantirish | ikki tab da qoldiq sinxron; chek o'zbek harflari bilan |
| 6 | Nasiya va to'lovlar | mijoz, kredit limiti, nasiya, to'lov taqsimlash, mijoz balansi, kassa smenasi, qo'lda kirim-chiqim, `payment.received`, `debt.overdue` (Celery), `credit_limit_warning` | mijozlar, qarzlar, to'lov qabul qilish, kassa va smena sahifalari, buxgalter bildirishnomalari | limitdan oshsa 409; to'lov buxgalter ekranida jonli |
| 7 | Ombor amallari | ko'chirish (draft→sent→received, farq), inventarizatsiya, qaytarish, hisobdan chiqarish, `transfer.*` | ko'chirish, inventarizatsiya, qaytarish, hisobdan chiqarish sahifalari, qabul qiluvchiga bildirishnoma | ko'chirish holati ikki nuqtada jonli |
| 8 | Hisobotlar va dashboard | `reports` reyestri, PDF (WeasyPrint + Noto Sans) va Excel (openpyxl) renderlari, Celery orqali og'ir hisobotlar, `report.ready`, dashboard selectorlari | hisobotlar sahifasi (filtr, yuklab olish), rahbar dashboardi (Recharts, jonli) | hisobotlar PDF/Excel; dashboard savdoda jonli yangilanadi |
| 9 | PWA va Tauri | — | vite-plugin-pwa (manifest, offline shell), Tauri o'rami (plugin-http bilan cookie), build skriptlari | PWA o'rnatiladi; Tauri desktop ishlaydi |
| 10 | Yakun | test qamrovini to'ldirish, OpenAPI sxemani tekshirish, README, `docs/` yangilash, seed ma'lumotlar | e2e tekshiruvlar, README | hammasi yashil |

Har bosqichda o'zgaradigan hujjatlar: `er-diagram.md`, `domain-events.md`, `realtime.md` (yangi turlar), `docs/api/openapi.yaml`.
