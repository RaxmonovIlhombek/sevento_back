# Rollar, huquqlar va nuqta chegarasi

> Holat: 0-bosqichda reja; 1–7-bosqichlarda amalga oshirilgan qismlari ✅ bilan belgilangan.

## 1. Model

- **Huquq (capability)** — kodda ro'yxatga olingan satr (`"sales.create"`), chunki u kodga bog'liq (qaysi endpoint nimani tekshiradi).
  Ro'yxat `accounts/capabilities.py` da, `GET /api/v1/auth/capabilities/` orqali ko'rish mumkin.
- **Rol** — MB jadvali `accounts.Role` (`code`, `name`, `capabilities: [..]`). Boshlang'ich 4 ta rol migratsiya bilan yaratiladi, rahbar admin panel / API orqali rol huquqlarini o'zgartira oladi va yangi rol qo'sha oladi.
  `is_system=true` rollar o'chirilmaydi (lekin huquqlari tahrirlanadi).
- **Nuqta chegarasi** — `UserBranch` (foydalanuvchi ↔ nuqta). `branches.view_all` huquqi bo'lsa chegara yo'q.
- Foydalanuvchining amaldagi huquqlari `GET /api/v1/auth/me/` javobida keladi: `{user, role, capabilities: [], branches: [{id, name, is_default}], all_branches: bool}` — frontend menyu va guard shu asosida.

## 2. Huquqlar ro'yxati (boshlang'ich)

| Huquq | Ma'nosi |
|---|---|
| `branches.view_all` | barcha nuqtalar ma'lumotini ko'rish (nuqta chegarasini olib tashlaydi) |
| `branches.manage` | nuqta yaratish/tahrirlash |
| `users.manage` | foydalanuvchi va rollarni boshqarish |
| `settings.manage` | tizim sozlamalari, valyutalar, to'lov turlari, o'lchov birliklari |
| `audit.view` | audit jurnalini ko'rish |
| `catalog.view` | tovar, kategoriya, narxlarni ko'rish |
| `catalog.manage` | tovar/kategoriya yaratish va tahrirlash |
| `catalog.prices.manage` | narxlarni o'zgartirish |
| `currency.rates.manage` | kursni qo'lda kiritish |
| `inventory.view` | qoldiq va harakatlar jurnali |
| `inventory.view_cost` | tannarx va partiya narxini ko'rish |
| `inventory.manage` | nuqta bo'yicha minimal qoldiqni o'zgartirish |
| `purchasing.view` / `purchasing.manage` | kirimlar |
| `inventory.transfers.create` / `inventory.transfers.receive` / `inventory.transfers.cancel` | ko'chirish |
| `inventory.counts.manage` | inventarizatsiya |
| `inventory.writeoffs.manage` | hisobdan chiqarish |
| `sales.view` / `sales.create` | savdo |
| `sales.discount` | chegirma berish (sozlamadagi chegaragacha) |
| `sales.discount.unlimited` | cheksiz chegirma |
| `sales.cancel` | yakunlangan savdoni bekor qilish |
| `sales.returns.create` | qaytarish |
| `sales.credit` | nasiyaga sotish |
| `payments.view` / `payments.receive` | to'lov qabul qilish |
| `payments.refund` | pul qaytarish |
| `cashbox.view` / `cashbox.manage` | kassa qoldig'i va jurnali; smena ochish/yopish, qo'lda kirim-chiqim (`manage`) |
| `customers.view` / `customers.manage` | mijozlar |
| `customers.credit_limit.manage` | kredit limitini o'zgartirish |
| `debts.view` / `debts.manage` | qarzlar, muddatni o'zgartirish |
| `reports.view` | hisobotlar |
| `reports.financial` | foyda, tannarx, kassa hisobotlari |
| `dashboard.view` | rahbar dashboardi |

## 3. Boshlang'ich rollar

| Huquq guruhi | `owner` Rahbar | `accountant` Buxgalter | `storekeeper` Omborchi | `seller` Sotuvchi |
|---|:-:|:-:|:-:|:-:|
| `branches.view_all` | ✔ | ✔ | — | — |
| `branches.manage`, `users.manage`, `settings.manage`, `audit.view` | ✔ | — | — | — |
| `catalog.view` | ✔ | ✔ | ✔ | ✔ |
| `catalog.manage` | ✔ | — | ✔ | — |
| `catalog.prices.manage`, `currency.rates.manage` | ✔ | ✔ | — | — |
| `inventory.view` | ✔ | ✔ | ✔ | ✔ (faqat qoldiq) |
| `inventory.view_cost` | ✔ | ✔ | ✔ | — |
| `purchasing.*` | ✔ | ko'rish | ✔ | — |
| `inventory.transfers.*` | ✔ | — | ✔ | — |
| `inventory.counts.manage`, `inventory.writeoffs.manage` | ✔ | — | ✔ | — |
| `sales.view` | ✔ | ✔ | — | ✔ (o'z nuqtasi) |
| `sales.create`, `sales.discount`, `sales.returns.create`, `sales.credit` | ✔ | — | — | ✔ |
| `sales.discount.unlimited`, `sales.cancel` | ✔ | — | — | — |
| `payments.view` | ✔ | ✔ | — | ✔ (o'ziniki) |
| `payments.receive` | ✔ | ✔ | — | ✔ |
| `payments.refund` | ✔ | ✔ | — | — |
| `cashbox.view` | ✔ | ✔ | — | ✔ (o'z nuqtasi) |
| `cashbox.manage` | ✔ | ✔ | — | — |
| `customers.view`, `customers.manage` | ✔ | ✔ | — | ✔ |
| `customers.credit_limit.manage` | ✔ | ✔ | — | — |
| `debts.view` | ✔ | ✔ | — | ✔ (o'z mijozlari) |
| `debts.manage` | ✔ | ✔ | — | — |
| `reports.view` | ✔ | ✔ | ✔ (ombor hisobotlari) | — |
| `reports.financial`, `dashboard.view` | ✔ | ✔ (dashboard: faqat moliya) | — | — |

Jadval boshlang'ich holat; rahbar o'zgartira oladi.

## 4. Backend da tekshiruv

Har endpointda uch qavat:

1. `IsAuthenticated` — JWT.
2. `HasCapability("sales.create")` — DRF permission klassi; ViewSet da `capability_map = {"list": "sales.view", "create": "sales.create", ...}`.
3. **Nuqta chegarasi:**
   - O'qish: barcha nuqtaga bog'liq selector lar `for_user(user)` ni qo'llaydi: `branches.view_all` bo'lmasa `branch_id IN user_branch_ids`.
     Bu ViewSet da `BranchScopedQuerySetMixin` orqali avtomatik; qo'lda yozilgan so'rov ham selector dan o'tadi.
   - Yozish: service funksiyasi `ensure_branch_access(actor, branch)` ni chaqiradi — begona nuqtaga yozish 403 `branch_forbidden`.
     Service darajasida tekshirilgani uchun view unutilsa ham himoya ishlaydi.
   - Ob'ekt darajasi: `GET /sales/{id}/` begona nuqtaniki bo'lsa — 404 (mavjudligini ham oshkor qilmaymiz).
4. Qo'shimcha ichki qoidalar service da: sotuvchi faqat **o'z** savdosini qaytara oladi (`sales.returns.create` + `sale.seller == actor`, yoki `sales.cancel`) ✅, kassa smenasi ochiq bo'lmasa naqd qabul qilinmaydi (`cashbox.require_open_shift`) va h.k.

Testlar: har app `tests/test_permissions.py` — 4 rol × asosiy endpointlar matritsasi, begona nuqta bilan 403/404.

## 5. Frontend da

- `useCapability("sales.create")` — menyu bandi va tugmalarni yashiradi.
- `<RequireCapability cap="reports.financial">` — route guard; huquq bo'lmasa `/403` sahifasi.
- Nuqta tanlagich: `all_branches=true` bo'lsa hamma nuqtalar + "Hammasi"; aks holda faqat biriktirilgan nuqtalar, bitta bo'lsa tanlagich ko'rinmaydi.
- Frontend yashirishi faqat qulaylik — backend har doim tekshiradi.

## Nasiya va kassa bo'yicha qo'shimcha qoidalar (6-bosqich)

- Mijozni sotuvchi ham yaratadi/tahrirlaydi (`customers.manage`), lekin kredit limiti va nasiya muddatini faqat `customers.credit_limit.manage` o'zgartiradi (maydon darajasida, service da tekshiriladi → 403 `credit_limit_forbidden`).
- Mijozlar barcha nuqtalar uchun umumiy (kredit qarori umumiy qarzga qarab); qarzlar ro'yxati va to'lovlar jurnali — nuqta chegarasi bilan.
- Qarz to'lovini qabul qilish — `payments.receive` (o'z nuqtasi kassasiga); qaytarish — `payments.refund` (faqat qarz to'lovi; savdo to'lovi — savdoni bekor qilib, `sales.cancel`).
- Nasiyaga sotish — `sales.credit` (403 `credit_forbidden`).

## Ombor hujjatlari va qaytarish bo'yicha qoidalar (7-bosqich)

- **Ko'chirish:** ko'rish — `inventory.transfers.create` / `.receive` yoki `inventory.view_cost` (birortasi); jo'natuvchi nuqta hamma hujjatlarini ko'radi, qabul qiluvchi nuqta — qoralamadan tashqari. Yaratish, tahrirlash, jo'natish — `inventory.transfers.create` + **jo'natuvchi** nuqtaga ruxsat; qabul — `inventory.transfers.receive` + **qabul qiluvchi** nuqtaga ruxsat; bekor qilish — `inventory.transfers.cancel` + jo'natuvchi nuqta. Qabul qiluvchi nuqta tanlovi uchun barcha faol nuqtalar ro'yxati — `GET /inventory/transfers/destinations/` (`inventory.transfers.create`). Hujjat javobidagi `allowed: {edit, send, receive, cancel}` — tugmalar uchun (service baribir qayta tekshiradi).
- **Inventarizatsiya:** ko'rish — `inventory.counts.manage` yoki `inventory.view_cost`; ochish, sanash, yakunlash, bekor qilish — `inventory.counts.manage` + nuqta.
- **Hisobdan chiqarish:** ko'rish — `inventory.writeoffs.manage` yoki `inventory.view_cost`; yaratish/bekor qilish — `inventory.writeoffs.manage` + nuqta. Sabablar ma'lumotnomasi — `settings.manage`.
- **Savdo qaytarish:** `sales.returns.create` + nuqta; sotuvchi faqat **o'z** savdosini qaytaradi, `sales.cancel` huquqi borlar nuqtadagi istalgan savdoni (403 `return_forbidden`). Pul qaytarish shu huquq bilan (alohida `payments.refund` shart emas). Qaytarish bo'lgan savdoni bekor qilib bo'lmaydi (409 `sale_has_returns`).
- Tannarx maydonlari (ko'chirish, inventarizatsiya, hisobdan chiqarish, qaytarish) `inventory.view_cost` bo'lmasa javobdan olib tashlanadi; WebSocket payload ida tannarx yo'q.

## Hisobotlar va dashboard bo'yicha qoidalar (8-bosqich)

- **Hisobotlar ro'yxati va eksport:** `reports.view` yoki `reports.financial` (birortasi). Har hisobotning o'z `capability` si bor: savdo, tovarlar bo'yicha foyda, qaytarish, to'lovlar, kassa oqimi, qarzlar — `reports.financial`; kirim — `purchasing.view`; ombor hisobotlari — `reports.view`. Ro'yxatda faqat ochiq hisobotlar; boshqasini so'rash — 403 `permission_denied`.
- **Ustun darajasi:** tannarx/qiymat ustunlari (`Column.capability = "inventory.view_cost"`) huquq bo'lmasa JSON, PDF va Excel dan olib tashlanadi.
- **Nuqta chegarasi:** `branch` filtri `ensure_branch_access` dan o'tadi (begona nuqta — 403); filtr bo'sh bo'lsa selectorlar foydalanuvchining nuqtalari bilan cheklanadi (`branches.view_all` — hammasi).
- **Fondagi fayllar:** `GET /reports/jobs/` va yuklab olish — faqat **o'zi so'ragan** `ReportJob` (boshqaniki 404); tayyor bo'lmasa 409 `report_not_ready`. `report.ready` WS xabari ham faqat so'raganga.
- **Dashboard:** `GET /reports/dashboard/` — `dashboard.view`. Foyda KPI va grafikdagi foyda chizig'i — faqat `reports.financial`; ombor qiymati — `inventory.view_cost`. Ma'lumot foydalanuvchi nuqtalari bilan cheklangan; `branch` parametri bilan bitta nuqta.
- Har bir eksport audit jurnaliga yoziladi (`report.exported`: hisobot, format, filtrlar, qatorlar soni).
