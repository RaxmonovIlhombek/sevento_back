# Rollar, huquqlar va nuqta chegarasi

> Holat: 0-bosqich — reja.

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
| `cashbox.view` / `cashbox.manage` | kassa, smena, qo'lda kirim-chiqim |
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
4. Qo'shimcha ichki qoidalar service da: sotuvchi faqat **o'z** savdosini qaytara oladi (`sales.returns.create` + `sale.seller == actor`, yoki `sales.cancel`), kassa smenasi ochiq bo'lmasa naqd qabul qilinmaydi va h.k.

Testlar: har app `tests/test_permissions.py` — 4 rol × asosiy endpointlar matritsasi, begona nuqta bilan 403/404.

## 5. Frontend da

- `useCapability("sales.create")` — menyu bandi va tugmalarni yashiradi.
- `<RequireCapability cap="reports.financial">` — route guard; huquq bo'lmasa `/403` sahifasi.
- Nuqta tanlagich: `all_branches=true` bo'lsa hamma nuqtalar + "Hammasi"; aks holda faqat biriktirilgan nuqtalar, bitta bo'lsa tanlagich ko'rinmaydi.
- Frontend yashirishi faqat qulaylik — backend har doim tekshiradi.
