# ER-diagramma

> Holat: 0-bosqich — reja. Maydon nomlari kodlashda sal o'zgarishi mumkin, lekin jadvallar va bog'lanishlar shu.

Umumiy kelishuvlar:

- Har jadvalda `id` (BigAutoField), `created_at`, `updated_at` (diagrammada ko'rsatilmagan).
- Pul: `decimal(20,4)`, kurs: `decimal(20,6)`, miqdor: `decimal(14,3)`.
- `*_base` — asosiy hisob valyutasidagi summa (sozlama `currency.base_code`, hozir USD).
- Moliyaviy hujjatlar `number` ga ega: `S-TSH1-26-000123` (tur-nuqta kodi-yil-tartib), `DocumentSequence` dan.
- Hujjatlar o'chirilmaydi, `status` orqali bekor qilinadi.

## 1. Umumiy ko'rinish (asosiy jadvallar)

```mermaid
erDiagram
  User }o--o{ Branch : "UserBranch"
  User }o--|| Role : ""
  Product }o--|| Category : ""
  Product }o--|| Unit : ""
  Product ||--o{ ProductPrice : ""
  ProductPrice }o--|| PriceType : ""
  ProductPrice }o--|| Currency : ""
  Currency ||--o{ ExchangeRate : ""

  Branch ||--o{ StockLevel : ""
  Product ||--o{ StockLevel : ""
  Branch ||--o{ Batch : ""
  Product ||--o{ Batch : ""
  Batch ||--o{ StockMovement : ""

  Supplier ||--o{ Purchase : ""
  Purchase ||--|{ PurchaseItem : ""
  Purchase ||--o{ PurchaseExpense : ""
  PurchaseItem ||--o| Batch : "partiya yaratadi"

  Branch ||--o{ Transfer : "from / to"
  Transfer ||--|{ TransferItem : ""
  Branch ||--o{ StockCount : ""
  Branch ||--o{ WriteOff : ""

  Customer ||--o{ Sale : ""
  Branch ||--o{ Sale : ""
  Sale ||--|{ SaleItem : ""
  Sale ||--o{ SaleReturn : ""
  Sale ||--o{ Payment : ""
  Sale ||--o| Debt : ""
  Customer ||--o{ Debt : ""
  Customer ||--o{ Payment : ""
  Payment }o--|| PaymentMethod : ""
  Payment ||--o{ DebtAllocation : ""
  Debt ||--o{ DebtAllocation : ""
  Payment ||--o| CashTransaction : ""
  Cashbox ||--o{ CashTransaction : ""
  Branch ||--o{ Cashbox : ""
  Customer ||--o{ CustomerLedgerEntry : ""
```

## 2. accounts, branches

```mermaid
erDiagram
  Role {
    int id PK
    string code UK "owner, accountant, storekeeper, seller"
    string name
    json capabilities "['sales.create', ...]"
    bool is_system "o'chirib bo'lmaydi"
  }
  User {
    int id PK
    string username UK
    string password
    string full_name
    string phone
    int role_id FK
    bool is_active
    datetime last_login
  }
  UserBranch {
    int id PK
    int user_id FK
    int branch_id FK
    bool is_default
  }
  Branch {
    int id PK
    string code UK "TSH1 — hujjat raqamida"
    string name
    string type "shop | warehouse"
    string address
    string phone
    json settings "chek sarlavhasi va h.k."
    bool is_active
  }
  Role ||--o{ User : ""
  User ||--o{ UserBranch : ""
  Branch ||--o{ UserBranch : ""
```

- `UserBranch` bo'sh + rolda `branches.view_all` → barcha nuqtalar (rahbar, buxgalter).
- Sotuvchi/omborchi kamida bitta `UserBranch` ga ega bo'lishi shart.

## 3. catalog, currency

```mermaid
erDiagram
  Category {
    int id PK
    int parent_id FK "null = ildiz"
    string name
    int sort_order
    bool is_active
  }
  Unit {
    int id PK
    string code UK "dona, kg, m, litr"
    string name
    int decimal_places "0 = faqat butun"
  }
  Product {
    int id PK
    string sku UK
    string barcode "indeks, null bo'lishi mumkin"
    string name
    int category_id FK
    int unit_id FK
    decimal min_quantity "null = sozlamadagi default"
    string description
    bool is_active
  }
  PriceType {
    int id PK
    string code UK "retail, wholesale"
    string name
    bool is_default
  }
  ProductPrice {
    int id PK
    int product_id FK
    int price_type_id FK
    int currency_id FK
    int branch_id FK "null = hamma nuqta"
    decimal amount
    datetime valid_from
  }
  Currency {
    int id PK
    string code UK "USD, UZS"
    string name
    string symbol
    int decimal_places
    bool is_active
  }
  ExchangeRate {
    int id PK
    int currency_id FK
    decimal rate "1 birlik = N UZS"
    date date
    string source "cbu | manual"
    int created_by_id FK
  }
  Category ||--o{ Category : "parent"
  Category ||--o{ Product : ""
  Unit ||--o{ Product : ""
  Product ||--o{ ProductPrice : ""
  PriceType ||--o{ ProductPrice : ""
  Currency ||--o{ ProductPrice : ""
  Currency ||--o{ ExchangeRate : ""
```

- `ProductPrice` — faqat qo'shiladi (tarix): amaldagi narx — eng so'nggi `valid_from <= now`; nuqtaga xos narx (`branch` to'ldirilgan) umumiy narxdan (`branch = null`) ustun. Indeks `(product, price_type, currency, branch, -valid_from)`.
- `ExchangeRate` da `UNIQUE (currency, date)` — kuniga bitta kurs; qo'lda kiritilgan kurs shu kungi CBU kursini almashtiradi (`source` qaysi manbadan ekanini saqlaydi). Kurs 6 xonagacha. UZS uchun kurs yozilmaydi (1).
- `Product.barcode` — bo'sh bo'lishi mumkin, to'ldirilganlari `UNIQUE` (qisman indeks); `sku` katta harfga keltiriladi.
- `Category` da `UNIQUE (parent, name)` (ildizlar uchun ham — `NULLS NOT DISTINCT`); sikl service da tekshiriladi.
- Seed: valyutalar USD (2 xona), UZS (0 xona); birliklar dona, kg, g, l, m, m2, qadoq; narx turlari Chakana (default), Ulgurji. Hammasi MB da, admin/API orqali o'zgaradi.
- 3-bosqichda amalga oshirildi; rejadan farq: `Currency.sort_order`, `PriceType.sort_order`, `Unit.is_active` qo'shildi.

## 4. inventory

```mermaid
erDiagram
  StockLevel {
    int id PK
    int branch_id FK
    int product_id FK
    decimal quantity "CHECK >= 0"
    decimal min_quantity "null = Product.min_quantity, keyin sozlama"
    bool below_minimum "chegaradan o'tishni aniqlash uchun"
    datetime updated_at
  }
  Batch {
    int id PK
    int branch_id FK
    int product_id FK
    string source_type "purchase, transfer, stock_count"
    bigint source_id "manba hujjat (FK emas: app lar bog'lanmasin)"
    bigint source_line_id "manba qatori, masalan PurchaseItem.id"
    string source_number "K-TSH1-26-000001"
    int parent_id FK "ko'chirishda asl partiya"
    datetime received_at "FIFO tartibi (received_at, id)"
    decimal quantity_initial
    decimal quantity_remaining "CHECK 0 <= remaining <= initial"
    decimal unit_cost_base "asosiy valyutada, 6 xona"
    datetime created_at
  }
  StockMovement {
    int id PK
    int branch_id FK
    int product_id FK
    int batch_id FK
    string type "purchase_in, purchase_cancel, sale_out, sale_cancel, sale_return_in, transfer_out, transfer_in, transfer_cancel, count_surplus, count_shortage, write_off, write_off_cancel"
    decimal quantity "ishorali: kirim +, chiqim -"
    decimal unit_cost_base
    decimal total_cost_base "ishorali"
    decimal balance_after "nuqta bo'yicha shu tovar qoldig'i"
    string document_type
    bigint document_id
    string document_number
    int created_by_id FK
    datetime created_at
  }
  Transfer {
    int id PK
    string number UK "KO-TSH1-26-000001 (jo'natuvchi nuqta kodi)"
    int from_branch_id FK
    int to_branch_id FK "CHECK from != to"
    string status "draft, sent, received, cancelled"
    decimal total_cost_base "jo'natishdagi FIFO tannarx"
    decimal shortage_cost_base "qabulda yetishmagan qism"
    bool has_discrepancy
    int created_by_id FK
    int sent_by_id FK
    datetime sent_at
    int received_by_id FK
    datetime received_at
    string receive_note
    int cancelled_by_id FK
    datetime cancelled_at
    string cancel_reason
    string note
  }
  TransferItem {
    int id PK
    int transfer_id FK
    int product_id FK
    decimal quantity "jo'natiladigan, CHECK > 0"
    decimal quantity_received "qabulda; CHECK 0..quantity"
    decimal unit_cost_base "jo'natishda FIFO dan (o'rtacha)"
    decimal total_cost_base
    json batch_allocations "[{batch_id, quantity, unit_cost_base}]"
  }
  StockCount {
    int id PK
    string number UK "INV-..."
    int branch_id FK "UNIQUE (branch) WHERE status=draft"
    int category_id FK "ixtiyoriy: faqat shu kategoriya"
    string status "draft, completed, cancelled"
    decimal surplus_cost_base
    decimal shortage_cost_base
    int created_by_id FK
    int completed_by_id FK
    datetime completed_at
    string note
  }
  StockCountItem {
    int id PK
    int count_id FK
    int product_id FK "UNIQUE (count, product)"
    decimal expected_quantity "yaratilganda; yakunlashda joriy qoldiq bilan yangilanadi"
    decimal counted_quantity "bo'sh — sanalmagan (yakunlashda o'tkazib yuboriladi)"
    decimal difference "counted - expected"
    decimal unit_cost_base
    decimal cost_difference_base
  }
  WriteOffReason {
    int id PK
    string code UK "damaged, expired, lost, internal, other, transfer_shortage"
    string name
    bool is_active
    bool is_system "transfer_shortage — qo'lda tanlanmaydi"
  }
  WriteOff {
    int id PK
    string number UK "HC-..."
    int branch_id FK
    int reason_id FK
    int transfer_id FK "ko'chirish kamomadi bo'lsa (qoldiqqa ta'sirsiz)"
    string status "completed, cancelled (yaratilishi bilan yakunlanadi)"
    decimal total_cost_base
    int created_by_id FK
    datetime completed_at
    int cancelled_by_id FK
    datetime cancelled_at
    string cancel_reason
    string note
  }
  WriteOffItem {
    int id PK
    int write_off_id FK
    int product_id FK
    decimal quantity
    decimal unit_cost_base
    decimal total_cost_base
    json batch_allocations
  }
  Batch ||--o{ StockMovement : ""

  Supplier ||--o{ Purchase : ""
  Purchase ||--|{ PurchaseItem : ""
  Purchase ||--o{ PurchaseExpense : ""
  PurchaseItem ||--o| Batch : "partiya yaratadi"

  Branch ||--o{ Transfer : "from / to"
  Transfer ||--|{ TransferItem : ""
  Branch ||--o{ StockCount : ""
  Branch ||--o{ WriteOff : ""

  Customer ||--o{ Sale : ""
  Branch ||--o{ Sale : ""
  Sale ||--|{ SaleItem : ""
  Sale ||--o{ SaleReturn : ""
  Sale ||--o{ Payment : ""
  Sale ||--o| Debt : ""
  Customer ||--o{ Debt : ""
  Customer ||--o{ Payment : ""
  Payment }o--|| PaymentMethod : ""
  Payment ||--o{ DebtAllocation : ""
  Debt ||--o{ DebtAllocation : ""
  Payment ||--o| CashTransaction : ""
  Cashbox ||--o{ CashTransaction : ""
  Branch ||--o{ Cashbox : ""
  Customer ||--o{ CustomerLedgerEntry : ""
```

## 2. accounts, branches

```mermaid
erDiagram
  Role {
    int id PK
    string code UK "owner, accountant, storekeeper, seller"
    string name
    json capabilities "['sales.create', ...]"
    bool is_system "o'chirib bo'lmaydi"
  }
  User {
    int id PK
    string username UK
    string password
    string full_name
    string phone
    int role_id FK
    bool is_active
    datetime last_login
  }
  UserBranch {
    int id PK
    int user_id FK
    int branch_id FK
    bool is_default
  }
  Branch {
    int id PK
    string code UK "TSH1 — hujjat raqamida"
    string name
    string type "shop | warehouse"
    string address
    string phone
    json settings "chek sarlavhasi va h.k."
    bool is_active
  }
  Role ||--o{ User : ""
  User ||--o{ UserBranch : ""
  Branch ||--o{ UserBranch : ""
```

- `UserBranch` bo'sh + rolda `branches.view_all` → barcha nuqtalar (rahbar, buxgalter).
- Sotuvchi/omborchi kamida bitta `UserBranch` ga ega bo'lishi shart.

## 3. catalog, currency

```mermaid
erDiagram
  Category {
    int id PK
    int parent_id FK "null = ildiz"
    string name
    int sort_order
    bool is_active
  }
  Unit {
    int id PK
    string code UK "dona, kg, m, litr"
    string name
    int decimal_places "0 = faqat butun"
  }
  Product {
    int id PK
    string sku UK
    string barcode "indeks, null bo'lishi mumkin"
    string name
    int category_id FK
    int unit_id FK
    decimal min_quantity "null = sozlamadagi default"
    string description
    bool is_active
  }
  PriceType {
    int id PK
    string code UK "retail, wholesale"
    string name
    bool is_default
  }
  ProductPrice {
    int id PK
    int product_id FK
    int price_type_id FK
    int currency_id FK
    int branch_id FK "null = hamma nuqta"
    decimal amount
    datetime valid_from
  }
  Currency {
    int id PK
    string code UK "USD, UZS"
    string name
    string symbol
    int decimal_places
    bool is_active
  }
  ExchangeRate {
    int id PK
    int currency_id FK
    decimal rate "1 birlik = N UZS"
    date date
    string source "cbu | manual"
    int created_by_id FK
  }
  Category ||--o{ Category : "parent"
  Category ||--o{ Product : ""
  Unit ||--o{ Product : ""
  Product ||--o{ ProductPrice : ""
  PriceType ||--o{ ProductPrice : ""
  Currency ||--o{ ProductPrice : ""
  Currency ||--o{ ExchangeRate : ""
```

- `ProductPrice` — faqat qo'shiladi (tarix): amaldagi narx — eng so'nggi `valid_from <= now`; nuqtaga xos narx (`branch` to'ldirilgan) umumiy narxdan (`branch = null`) ustun. Indeks `(product, price_type, currency, branch, -valid_from)`.
- `ExchangeRate` da `UNIQUE (currency, date)` — kuniga bitta kurs; qo'lda kiritilgan kurs shu kungi CBU kursini almashtiradi (`source` qaysi manbadan ekanini saqlaydi). Kurs 6 xonagacha. UZS uchun kurs yozilmaydi (1).
- `Product.barcode` — bo'sh bo'lishi mumkin, to'ldirilganlari `UNIQUE` (qisman indeks); `sku` katta harfga keltiriladi.
- `Category` da `UNIQUE (parent, name)` (ildizlar uchun ham — `NULLS NOT DISTINCT`); sikl service da tekshiriladi.
- Seed: valyutalar USD (2 xona), UZS (0 xona); birliklar dona, kg, g, l, m, m2, qadoq; narx turlari Chakana (default), Ulgurji. Hammasi MB da, admin/API orqali o'zgaradi.
- 3-bosqichda amalga oshirildi; rejadan farq: `Currency.sort_order`, `PriceType.sort_order`, `Unit.is_active` qo'shildi.

## 4. inventory

```mermaid
erDiagram
  StockLevel {
    int id PK
    int branch_id FK
    int product_id FK
    decimal quantity "CHECK >= 0"
    decimal min_quantity "null = Product.min_quantity, keyin sozlama"
    bool below_minimum "chegaradan o'tishni aniqlash uchun"
    datetime updated_at
  }
  Batch {
    int id PK
    int branch_id FK
    int product_id FK
    string source_type "purchase, transfer, stock_count"
    bigint source_id "manba hujjat (FK emas: app lar bog'lanmasin)"
    bigint source_line_id "manba qatori, masalan PurchaseItem.id"
    string source_number "K-TSH1-26-000001"
    int parent_id FK "ko'chirishda asl partiya"
    datetime received_at "FIFO tartibi (received_at, id)"
    decimal quantity_initial
    decimal quantity_remaining "CHECK 0 <= remaining <= initial"
    decimal unit_cost_base "asosiy valyutada, 6 xona"
    datetime created_at
  }
  StockMovement {
    int id PK
    int branch_id FK
    int product_id FK
    int batch_id FK
    string type "purchase_in, purchase_cancel, sale_out, sale_cancel, sale_return_in, transfer_out, transfer_in, transfer_cancel, count_surplus, count_shortage, write_off, write_off_cancel"
    decimal quantity "ishorali: kirim +, chiqim -"
    decimal unit_cost_base
    decimal total_cost_base "ishorali"
    decimal balance_after "nuqta bo'yicha shu tovar qoldig'i"
    string document_type
    bigint document_id
    string document_number
    int created_by_id FK
    datetime created_at
  }
  Transfer {
    int id PK
    string number UK
    int from_branch_id FK
    int to_branch_id FK
    string status "draft, sent, received, cancelled"
    int created_by_id FK
    int sent_by_id FK
    datetime sent_at
    int received_by_id FK
    datetime received_at
    string note
  }
  TransferItem {
    int id PK
    int transfer_id FK
    int product_id FK
    decimal quantity_sent
    decimal quantity_received "qabulda kiritiladi"
    decimal unit_cost_base "jo'natishda FIFO dan"
    json batch_allocations "[{batch_id, quantity, unit_cost_base}]"
  }
  StockCount {
    int id PK
    string number UK
    int branch_id FK
    string status "draft, in_progress, completed, cancelled"
    int created_by_id FK
    int completed_by_id FK
    datetime completed_at
    string note
  }
  StockCountItem {
    int id PK
    int stock_count_id FK
    int product_id FK
    decimal expected_quantity "boshlanganda qotiriladi"
    decimal counted_quantity
    decimal difference
    decimal unit_cost_base
  }
  WriteOffReason {
    int id PK
    string code UK
    string name
  }
  WriteOff {
    int id PK
    string number UK
    int branch_id FK
    int reason_id FK
    string status "draft, completed, cancelled"
    int created_by_id FK
    datetime completed_at
    decimal total_cost_base
    string note
  }
  WriteOffItem {
    int id PK
    int write_off_id FK
    int product_id FK
    decimal quantity
    decimal unit_cost_base
  }
  Batch ||--o{ StockMovement : ""
  Transfer ||--|{ TransferItem : ""
  Transfer ||--o| WriteOff : "kamomad"
  StockCount ||--|{ StockCountItem : ""
  WriteOff ||--|{ WriteOffItem : ""
  WriteOffReason ||--o{ WriteOff : ""
```

- `StockLevel`: `UNIQUE (branch, product)`, `CHECK (quantity >= 0)`. Manfiy qoldiq **yo'q** (rejadagi `allow_negative_stock` sozlamasi olib tashlandi: FIFO partiyasiz chiqimni tannarxsiz qoldirardi).
- `StockLevel.quantity` doim `SUM(Batch.quantity_remaining)` ga teng — bu invariantni test tekshiradi.
- `StockMovement` — faqat `INSERT`; har qoldiq o'zgarishi bitta qator (chiqim bir nechta partiyadan bo'lsa — har partiyaga bitta qator). Hisobotlar va "tovar kartasi" shu jadvaldan.
- Bir vaqtdagi chiqimlar: avval `StockLevel` keyin partiyalar `SELECT ... FOR UPDATE` bilan qulflanadi (doim shu tartibda — deadlock bo'lmasin).
- `Batch.source_*` — umumiy havola (`GenericForeignKey` emas, oddiy maydonlar): inventory boshqa app modellarini bilmaydi. Bekor qilishda `reverse_receipt(doc_type, doc_id)` shu maydonlar bo'yicha partiyalarni topadi.
- 4-bosqichda: `StockLevel`, `Batch`, `StockMovement`; 7-bosqichda: `Transfer`, `StockCount`, `WriteOff` (+ qatorlar, sabablar).
- Ko'chirish jo'natilganda manbadan FIFO chiqim (`transfer_out`), partiyalar `batch_allocations` ga yoziladi. Qabulda qabul qiluvchi nuqtada har manba partiya uchun yangi `Batch` (`parent` — manba partiya, `source_type=transfer`) asl tannarx bilan. Kam kelgan qism (FIFO tartibida oxirgisi) — "yo'lda yo'qolgan": avtomatik `WriteOff` (sabab `transfer_shortage`, `transfer_id` bilan), tovar kelmagani uchun qoldiq harakati yo'q; rahbarga xabar ketadi. Jo'natilgan ko'chirish bekor qilinsa — tovar manbadagi **asl partiyalarga** (`transfer_cancel`).
- Inventarizatsiya yakunlanganda har sanalgan qator joriy qoldiq bilan (qulf ostida) solishtiriladi: ortiqcha — yangi partiya (`count_surplus`, tannarx: shu nuqtadagi oxirgi partiya, bo'lmasa boshqa nuqtadagi, yoki 0), kamomad — FIFO chiqim (`count_shortage`). Sanash paytidagi savdolar shu tariqa hisobga olinadi.
- Hisobdan chiqarish yaratilishi bilan FIFO chiqim (`write_off`); bekor qilish — asl partiyalarga (`write_off_cancel`).

## 5. purchasing

```mermaid
erDiagram
  Supplier {
    int id PK
    string name
    string phone
    string contact_person
    string tin "STIR"
    string address
    string note
    bool is_active
  }
  Purchase {
    int id PK
    string number UK "K-<nuqta>-<yil>-<raqam>"
    int branch_id FK
    int supplier_id FK
    string status "draft, received, cancelled"
    string invoice_number
    date invoice_date
    int currency_id FK
    decimal rate_to_base "1 kirim valyutasi = N asosiy; qabulda qotiriladi"
    decimal subtotal "kirim valyutasida"
    decimal subtotal_base
    decimal expenses_total_base
    decimal total_base
    int created_by_id FK
    int received_by_id FK
    datetime received_at
    int cancelled_by_id FK
    datetime cancelled_at
    string cancel_reason
    string note
  }
  PurchaseItem {
    int id PK
    int purchase_id FK
    int product_id FK
    int position
    decimal quantity "birlik aniqligi tekshiriladi (dona 0, kg 3 xona)"
    decimal unit_price "kirim valyutasida"
    decimal line_total
    decimal line_total_base
    decimal allocated_expense_base
    decimal landed_unit_cost_base "(line_total_base + ulush) / miqdor, 6 xona"
  }
  ExpenseType {
    int id PK
    string code UK "transport, customs, loading"
    string name
    string default_allocation "by_value | by_quantity"
    bool is_active
  }
  PurchaseExpense {
    int id PK
    int purchase_id FK
    int expense_type_id FK
    int currency_id FK
    decimal amount
    string allocation_method
    decimal rate_to_base
    decimal amount_base
    string note
  }
  Supplier ||--o{ Purchase : ""
  Purchase ||--|{ PurchaseItem : ""
  Purchase ||--o{ PurchaseExpense : ""
  ExpenseType ||--o{ PurchaseExpense : ""
```

- `draft` → `received` o'tishida: shu kungi kurs qotiriladi, xarajatlar taqsimlanadi (`distribute` — 0,0001 gacha pastga yaxlitlab, qoldiq eng katta ulushga: yig'indi doim aniq), `landed_unit_cost_base` hisoblanadi, `inventory.services.receive_stock()` har qator uchun `Batch` yaratadi, `purchase.received` hodisasi. Takroriy so'rov `Idempotency-Key` bilan bir marta bajariladi.
- `draft` → `cancelled` doim; `received` → `cancelled` faqat partiyalardan hali hech narsa chiqmagan bo'lsa (`quantity_remaining == quantity_initial`), aks holda 409 `batch_consumed`. Bekor qilishda `purchase_cancel` harakatlari yoziladi.
- Kurs yo'q bo'lsa (kirim yoki xarajat valyutasi uchun) oldindan hisob ham, qabul ham 409 `rate_unavailable`.
- Seed: xarajat turlari Transport (qiymat bo'yicha), Bojxona (qiymat bo'yicha), Yuklash-tushirish (miqdor bo'yicha).
- Yetkazib beruvchiga qarz/to'lov hisobi MVP da yo'q, keyin `SupplierPayment` qo'shilishi uchun joy qoldirilgan (`payments` da `direction` va `counterparty_type` maydonlari).

## 6. sales

```mermaid
erDiagram
  Sale {
    int id PK
    string number UK "S-<nuqta>-<yil>-<raqam>"
    int branch_id FK
    int seller_id FK
    int price_type_id FK
    int customer_id FK "nasiyada majburiy, to'liq to'lovda ixtiyoriy"
    string status "completed, cancelled"
    int currency_id FK "savdo valyutasi"
    decimal rate_to_base "1 savdo valyutasi = N asosiy; savdo paytida qotiriladi"
    decimal subtotal "chegirmasiz"
    decimal discount_total
    decimal total
    decimal total_base
    decimal cost_base "FIFO tannarx yig'indisi"
    decimal paid_total "to'lovlar savdo valyutasida (4 xona)"
    decimal change_amount "qaytim, savdo valyutasida"
    decimal debt_amount "nasiya (payments.Debt)"
    date due_date
    decimal returned_total "qaytarishlar yig'indisi (savdo valyutasida)"
    decimal returned_total_base "savdo kursi bilan"
    decimal returned_cost_base "qaytgan tovar tannarxi; foyda = (total_base - returned_total_base) - (cost_base - returned_cost_base)"
    datetime completed_at
    int cancelled_by_id FK
    datetime cancelled_at
    string cancel_reason
    string note
  }
  SaleItem {
    int id PK
    int sale_id FK
    int product_id FK
    int position
    decimal quantity "CHECK > 0, birlik aniqligi"
    decimal unit_price "katalogdan, savdo valyutasida (serverda aniqlanadi)"
    decimal discount_amount "CHECK >= 0"
    decimal line_total "yaxlitlash(miqdor x narx) - chegirma"
    decimal cost_base "shu qator tannarxi"
    json batch_allocations "[{batch_id, quantity, unit_cost_base}]"
    decimal returned_quantity "CHECK 0..quantity"
  }
  SaleReturn {
    int id PK
    string number UK "Q-<nuqta>-<yil>-<raqam>"
    int sale_id FK
    int branch_id FK
    int customer_id FK "savdo mijozi"
    int currency_id FK "savdo valyutasi"
    decimal total "qator ulushlari: round(L(r+q)/Q) - round(Lr/Q)"
    decimal total_base "savdo kursi bilan"
    decimal cost_base "asl partiyalar tannarxi"
    decimal debt_reduction "avval savdo qarzidan ayirildi"
    decimal refund_amount "qolgani mijozga (default naqd)"
    int refund_method_id FK
    string reason
    int created_by_id FK
    datetime created_at
  }
  SaleReturnItem {
    int id PK
    int sale_return_id FK
    int sale_item_id FK
    int product_id FK
    decimal quantity
    decimal amount
    decimal cost_base
    json batch_allocations "asl partiyalarga qaytgani (oxirgisidan boshlab)"
  }
  Sale ||--|{ SaleItem : ""
  Sale ||--o{ SaleReturn : ""
  SaleReturn ||--|{ SaleReturnItem : ""
  SaleItem ||--o{ SaleReturnItem : ""
```

- 5–6-bosqichda amalga oshirildi: `Sale` (+ `customer_id`, `debt_amount`, `due_date`), `SaleItem`. Qaytarish (`SaleReturn`) — 7-bosqich.
- Nasiya: to'lov jamidan kam bo'lsa va mijoz tanlangan bo'lsa qolgani `payments.services.register_debt()` bilan qarz bo'ladi (`sales.credit` huquqi, kredit limiti — oshsa 409 `credit_limit_exceeded`, tovar chiqimidan oldin tekshiriladi). Qarz kasr qoldig'i yuqoriga yaxlitlanadi; muddat — kiritilgan (bugundan oldin emas) yoki mijoz/sozlama defaulti.
- Savdo bitta so'rovda va bitta tranzaksiyada yakunlanadi: narx (katalog; savdo valyutasida bo'lmasa — sozlama ruxsat bersa — joriy kurs bilan o'tkaziladi) → chegirma tekshiruvi → FIFO chiqim (`inventory.services.issue_stock`, tovar id tartibida qulflanadi) → to'lovlar (`payments.services.receive_payment`) → qaytim (`give_change`, faqat naqd) → `sale.completed`.
- Narxni server belgilaydi (kassir narxni o'zgartira olmaydi). Mijoz ekrandagi jamini `expected_total` sifatida yuboradi; farq bo'lsa 409 `total_mismatch` (narx o'zgargan).
- Bekor qilish (`sales.cancel`): nasiya bekor qilinadi (to'lov qilingan bo'lsa 409 `debt_has_payments`), tovar **asl partiyalarga** qaytadi (`inventory.services.restore_stock`, `sale_cancel` harakati, tannarx saqlanadi), to'lovlar teskari yoziladi (`payments.services.reverse_document_payments`). Kassada naqd yetmasa — 409 `insufficient_cash`.

## 7. payments

```mermaid
erDiagram
  PaymentMethod {
    int id PK
    string code UK "cash, card, transfer (keyin click, payme)"
    string name
    string provider "providers reyestri: manual (keyin click, payme)"
    bool is_cash "kassa qoldig'iga ta'sir qiladimi"
    bool is_active
    int sort_order
  }
  Cashbox {
    int id PK
    int branch_id FK
    int currency_id FK
    string name
    decimal balance "CHECK >= 0"
    bool is_active
  }
  CashFlowCategory {
    int id PK
    string code UK "sale, refund, debt_payment, expense, deposit, withdrawal, adjustment"
    string name
    string direction "in | out | both"
    bool is_manual "qo'lda kiritiladimi (deposit, withdrawal, expense)"
  }
  CashShift {
    int id PK
    int branch_id FK "nuqtada bitta ochiq smena (partial UNIQUE)"
    string status "open | closed"
    int opened_by_id FK
    datetime opened_at
    int closed_by_id FK
    datetime closed_at
    string note
  }
  CashShiftBalance {
    int id PK
    int shift_id FK
    int cashbox_id FK "har valyuta kassasi"
    decimal opening_balance
    decimal expected_balance
    decimal actual_balance "sanalgan"
    decimal difference
  }
  CashTransaction {
    int id PK
    int cashbox_id FK
    int shift_id FK "ochiq smena bo'lsa"
    string direction "in | out"
    int category_id FK
    decimal amount "CHECK > 0"
    decimal balance_after "CHECK >= 0"
    int payment_id FK "null = qo'lda yozuv yoki smena farqi"
    string document_type
    bigint document_id
    string document_number
    int created_by_id FK
    string note
  }
  Customer {
    int id PK
    string name
    string phone
    string tin
    string address
    decimal credit_limit_base "asosiy valyutada; null = sozlama"
    int default_due_days "null = sozlama"
    bool is_active
    string note
  }
  Payment {
    int id PK
    string number UK "T-<nuqta>-<yil>-<raqam>"
    int branch_id FK
    int method_id FK
    int customer_id FK "nasiya mijozi, qarz to'lovi"
    string kind "payment, change, refund, change_return"
    string direction "in | out"
    int currency_id FK
    decimal amount "CHECK > 0"
    decimal rate_to_base
    decimal amount_base
    string status "completed | reversed"
    int reversal_of_id FK "teskari yozuv (1:1)"
    string provider_reference
    string document_type "sale | customer (qarz to'lovi)"
    bigint document_id
    string document_number
    int received_by_id FK
    datetime received_at
    string note
  }
  Debt {
    int id PK
    int customer_id FK
    int branch_id FK
    int currency_id FK "savdo valyutasi — qarz shu valyutada qoladi"
    decimal amount "CHECK > 0"
    decimal paid_amount "0 <= paid <= amount - returned"
    decimal returned_amount "qaytarilgan tovar summasi (7-bosqich)"
    date due_date
    string status "open, paid, cancelled (muddati o'tgani — due_date < bugun)"
    string document_type "sale"
    bigint document_id
    string document_number
    datetime overdue_notified_at "debt.overdue bir marta"
    datetime settled_at
    int created_by_id FK
  }
  DebtAllocation {
    int id PK
    int payment_id FK
    int debt_id FK
    decimal amount "qarz valyutasida"
    decimal payment_amount "to'lov valyutasida"
  }
  CustomerLedgerEntry {
    int id PK
    int customer_id FK
    int currency_id FK
    string type "debt, payment, refund, cancel, return"
    decimal amount "ishorali: qarz +, to'lov -"
    decimal balance_after "mijoz x valyuta qarz qoldig'i"
    int debt_id FK
    int payment_id FK
    string document_type
    bigint document_id
    string document_number
    int created_by_id FK
  }
  Cashbox ||--o{ CashTransaction : ""
  CashShift ||--|{ CashShiftBalance : ""
  CashShift ||--o{ CashTransaction : ""
  CashFlowCategory ||--o{ CashTransaction : ""
  PaymentMethod ||--o{ Payment : ""
  Payment ||--o{ CashTransaction : ""
  Customer ||--o{ Payment : ""
  Customer ||--o{ Debt : ""
  Payment ||--o{ DebtAllocation : ""
  Debt ||--o{ DebtAllocation : ""
  Customer ||--o{ CustomerLedgerEntry : ""
```

- 5–6-bosqichda amalga oshirildi. Rejadan farqlar: `Payment` da `sale_id` o'rniga umumiy `document_type/document_id/document_number` (payments savdoni bilmaydi — bog'liqlik yo'nalishi sales → payments); `kind` va `reversal_of` (teskari yozuvlar); `Debt.status` da `partially_paid`/`overdue` yo'q — qisman to'langani `paid_amount > 0`, muddati o'tgani `due_date < bugun` dan hisoblanadi; smena **nuqta** bo'yicha (barcha valyutalar bitta smenada, qoldiqlar `CashShiftBalance` da).
- Kassa: har nuqta × valyuta uchun alohida `Cashbox`, birinchi naqd harakatda avtomatik yaratiladi. Faqat `PaymentMethod.is_cash=true` to'lovlar kassa qoldig'ini o'zgartiradi. Qaytim ham `Payment` (`kind=change`, naqd, `out`).
- Nasiya: `register_debt` mijoz qatorini qulflaydi (`select_for_update`) — bir mijozga parallel nasiyalar limitni chetlab o'tolmaydi. Limit asosiy valyutada; ochiq qarzlar **joriy kurs** bilan yig'iladi. Limit sozlamasi: mijozda yoki `payments.default_credit_limit_base` (default 0 — nasiya yo'q).
- Qarz to'lovi FIFO: eng eski muddatdan boshlab yopiladi (yoki tanlangan qarzlar), boshqa valyutadagi to'lov to'lov paytidagi kurs bilan o'tkaziladi; qarzdan ortiq summa rad etiladi (to'lov valyutasining bitta eng kichik birligidan kam yaxlitlash qoldig'i e'tiborsiz). To'liq yopish summasi — `GET customers/<id>/payoff/?currency=`.
- Qarz to'lovini qaytarish (`payments.refund`): qarzlar qayta ochiladi, mijoz hisobiga `refund` yozuvi, naqd bo'lsa kassadan chiqim. Savdo to'lovi — faqat savdoni bekor qilish orqali.
- Tovar qaytarish (7-bosqich): summa avval savdo qarzidan ayiriladi (`Debt.returned_amount`, mijoz hisobiga `return` yozuvi, qoldiq 0 bo'lsa qarz yopiladi), qolgani `refund_to_customer` bilan mijozga (default naqd, kassadan; `Payment.kind=refund`, `reversal_of` bo'sh, hujjat — `sale_return`). Qarz qoldig'i hamma joyda `amount - paid_amount - returned_amount`.
- Smena yopilganda sanalgan va kutilgan farqi `adjustment` kassa yozuvi bilan tenglashtiriladi — tizimdagi qoldiq doim haqiqiy naqdga teng. Sozlama `cashbox.require_open_shift=true` bo'lsa naqd harakat faqat ochiq smenada.

## 8. core, audit, reports

```mermaid
erDiagram
  OutboxEvent {
    int id PK
    string name
    string aggregate_type
    int aggregate_id
    json payload
    int actor_id
    int branch_id
    string status "pending, dispatched, failed"
    int attempts
    string last_error
    datetime occurred_at
    datetime dispatched_at
  }
  SystemSetting {
    int id PK
    string key UK
    json value
    string description
    int updated_by_id FK
  }
  DocumentSequence {
    int id PK
    string doc_type "S, P, T, R, PM, WO, SC"
    int branch_id FK
    int year
    int last_number
  }
  IdempotencyRecord {
    int id PK
    string key
    int user_id FK
    string method
    string path
    int response_status
    json response_body
    datetime created_at
  }
  AuditLog {
    int id PK
    int actor_id FK
    int branch_id FK
    string event_name
    string aggregate_type
    int aggregate_id
    json payload
    string ip
    string user_agent
    string request_id
    datetime created_at
  }
  ReportJob {
    int id PK
    string report_key
    string title
    json params
    string format "pdf | xlsx"
    string status "pending, running, ready, failed"
    file file "reports/YYYY/MM/"
    int rows_count
    string error
    int requested_by_id FK
    datetime created_at
    datetime started_at
    datetime finished_at
  }
```

- `IdempotencyRecord`: `UNIQUE (key, user_id)`; 24 soatdan keyin tozalanadi.
- `DocumentSequence`: `UNIQUE (doc_type, branch_id, year)`.
