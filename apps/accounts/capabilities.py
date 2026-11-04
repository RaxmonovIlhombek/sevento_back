"""Huquqlar (capability) ro'yxati — kodga bog'liq, shuning uchun kodda. Rollar MB da.

Yangi endpoint yangi huquq talab qilsa shu yerga qo'shiladi; rol preset lari boshlang'ich
holat uchun (bootstrap / data migration), keyin rahbar MB da o'zgartiradi.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Capability:
    code: str
    name: str
    group: str


CAPABILITIES: tuple[Capability, ...] = (
    # tizim
    Capability("branches.view_all", "Barcha nuqtalarni ko'rish", "Tizim"),
    Capability("branches.manage", "Nuqtalarni boshqarish", "Tizim"),
    Capability("users.manage", "Foydalanuvchi va rollarni boshqarish", "Tizim"),
    Capability("settings.manage", "Tizim sozlamalari", "Tizim"),
    Capability("audit.view", "Audit jurnalini ko'rish", "Tizim"),
    Capability("workflow.manage", "Tasdiqlash qoidalari va barcha so'rovlar", "Tizim"),
    # katalog
    Capability("catalog.view", "Katalogni ko'rish", "Katalog"),
    Capability("catalog.manage", "Tovar va kategoriyalarni boshqarish", "Katalog"),
    Capability("catalog.prices.manage", "Narxlarni o'zgartirish", "Katalog"),
    Capability("currency.rates.manage", "Valyuta kursini kiritish", "Katalog"),
    # ombor
    Capability("inventory.view", "Qoldiq va harakatlarni ko'rish", "Ombor"),
    Capability("inventory.view_cost", "Tannarxni ko'rish", "Ombor"),
    Capability("inventory.manage", "Qoldiq sozlamalari (nuqta bo'yicha minimal qoldiq)", "Ombor"),
    Capability("purchasing.view", "Kirimlarni ko'rish", "Ombor"),
    Capability("purchasing.manage", "Kirim qilish", "Ombor"),
    Capability("inventory.transfers.create", "Ko'chirish yaratish va jo'natish", "Ombor"),
    Capability("inventory.transfers.receive", "Ko'chirishni qabul qilish", "Ombor"),
    Capability("inventory.transfers.cancel", "Ko'chirishni bekor qilish", "Ombor"),
    Capability("inventory.counts.manage", "Inventarizatsiya", "Ombor"),
    Capability("inventory.writeoffs.manage", "Hisobdan chiqarish", "Ombor"),
    # savdo
    Capability("sales.view", "Savdolarni ko'rish", "Savdo"),
    Capability("sales.create", "Savdo qilish", "Savdo"),
    Capability("sales.discount", "Chegirma berish (chegaragacha)", "Savdo"),
    Capability("sales.discount.unlimited", "Cheksiz chegirma", "Savdo"),
    Capability("sales.cancel", "Savdoni bekor qilish", "Savdo"),
    Capability("sales.returns.create", "Qaytarish", "Savdo"),
    Capability("sales.credit", "Nasiyaga sotish", "Savdo"),
    # to'lov va kassa
    Capability("payments.view", "To'lovlarni ko'rish", "To'lovlar"),
    Capability("payments.receive", "To'lov qabul qilish", "To'lovlar"),
    Capability("payments.refund", "Pul qaytarish", "To'lovlar"),
    Capability("cashbox.view", "Kassani ko'rish", "To'lovlar"),
    Capability("cashbox.manage", "Kassa: smena, qo'lda kirim-chiqim", "To'lovlar"),
    Capability("customers.view", "Mijozlarni ko'rish", "To'lovlar"),
    Capability("customers.manage", "Mijozlarni boshqarish", "To'lovlar"),
    Capability("customers.credit_limit.manage", "Kredit limitini o'zgartirish", "To'lovlar"),
    Capability("debts.view", "Qarzlarni ko'rish", "To'lovlar"),
    Capability("debts.manage", "Qarzlarni boshqarish", "To'lovlar"),
    # hisobotlar
    Capability("reports.view", "Hisobotlar", "Hisobotlar"),
    Capability("reports.financial", "Moliyaviy hisobotlar (foyda, tannarx, kassa)", "Hisobotlar"),
    Capability("dashboard.view", "Rahbar dashboardi", "Hisobotlar"),
    # kadrlar
    Capability("hr.view", "Xodimlar va bo'limlarni ko'rish", "Kadrlar"),
    Capability("hr.manage", "Xodimlar va bo'limlarni boshqarish", "Kadrlar"),
    Capability("payroll.view", "Ish haqi ro'yxatini ko'rish", "Kadrlar"),
    Capability("payroll.manage", "Ish haqi hisoblash va to'lash", "Kadrlar"),
    # moliya (buxgalteriya)
    Capability("accounting.view", "Hisob rejasi, jurnal va sinov balansi", "Moliya"),
    Capability("accounting.manage", "Buxgalteriya yozuvlarini kiritish va o'zgartirish", "Moliya"),
    # CRM va ishlab chiqarish
    Capability("crm.view", "Lidlar va bitimlarni ko'rish", "CRM"),
    Capability("crm.manage", "Lidlar va bitimlarni boshqarish", "CRM"),
    Capability(
        "manufacturing.view", "BOM va ishlab chiqarish buyurtmalarini ko'rish", "Ishlab chiqarish"
    ),
    Capability("manufacturing.manage", "Ishlab chiqarishni boshqarish", "Ishlab chiqarish"),
    # yetkazish (kuryer)
    Capability("deliveries.view", "Yetkazishlarni ko'rish (o'ziga biriktirilgan)", "Yetkazish"),
    Capability("deliveries.manage", "Yetkazish holatini yangilash", "Yetkazish"),
    # buyurtma jarayoni: omborchi → operator → kuryer
    Capability(
        "fulfillment.view", "Yetkazish jarayonini kuzatish (nuqtadagi hammasi)", "Yetkazish"
    ),
    Capability("fulfillment.pack", "Buyurtmani taxlash (omborchi)", "Yetkazish"),
    Capability("fulfillment.verify", "Taxlanganini tekshirish (operator)", "Yetkazish"),
    Capability("fulfillment.manage", "Yetkazishni bekor qilish va boshqarish", "Yetkazish"),
    Capability("hr.staff.manage", "O'z nuqtasi xodimlarini yollash va boshqarish", "Kadrlar"),
)

CAPABILITY_CODES: frozenset[str] = frozenset(c.code for c in CAPABILITIES)
_BY_CODE = {c.code: c for c in CAPABILITIES}


def get_capability(code: str) -> Capability:
    return _BY_CODE[code]


def validate_codes(codes) -> list[str]:
    """Noma'lum kodlar ro'yxatini qaytaradi (bo'sh = hammasi to'g'ri)."""
    return sorted(set(codes) - CAPABILITY_CODES)


ALL = sorted(CAPABILITY_CODES)

ROLE_PRESETS: dict[str, dict] = {
    "owner": {"name": "Rahbar", "capabilities": ALL},
    "accountant": {
        "name": "Buxgalter",
        "capabilities": [
            "branches.view_all",
            "catalog.view",
            "catalog.prices.manage",
            "currency.rates.manage",
            "inventory.view",
            "inventory.view_cost",
            "purchasing.view",
            "sales.view",
            "payments.view",
            "payments.receive",
            "payments.refund",
            "cashbox.view",
            "cashbox.manage",
            "customers.view",
            "customers.manage",
            "customers.credit_limit.manage",
            "debts.view",
            "debts.manage",
            "reports.view",
            "reports.financial",
            "dashboard.view",
        ],
    },
    "storekeeper": {
        "name": "Omborchi",
        "capabilities": [
            "catalog.view",
            "catalog.manage",
            "inventory.view",
            "inventory.view_cost",
            "inventory.manage",
            "purchasing.view",
            "purchasing.manage",
            "inventory.transfers.create",
            "inventory.transfers.receive",
            "inventory.transfers.cancel",
            "inventory.counts.manage",
            "inventory.writeoffs.manage",
            "reports.view",
            "fulfillment.pack",
        ],
    },
    "seller": {
        "name": "Sotuvchi",
        "capabilities": [
            "catalog.view",
            "inventory.view",
            "sales.view",
            "sales.create",
            "sales.discount",
            "sales.returns.create",
            "sales.credit",
            "payments.view",
            "payments.receive",
            "cashbox.view",
            "customers.view",
            "customers.manage",
            "debts.view",
        ],
    },
    "hr_manager": {
        "name": "Kadrlar bo'limi (HR)",
        "capabilities": [
            "branches.view_all",
            "hr.view",
            "hr.manage",
            "payroll.view",
            "payroll.manage",
        ],
    },
    "branch_manager": {
        "name": "Filial rahbari",
        "capabilities": [
            "catalog.view",
            "inventory.view",
            "purchasing.view",
            "sales.view",
            "sales.create",
            "sales.discount",
            "sales.returns.create",
            "sales.credit",
            "payments.view",
            "payments.receive",
            "cashbox.view",
            "cashbox.manage",
            "customers.view",
            "customers.manage",
            "debts.view",
            "reports.view",
            "dashboard.view",
            "hr.view",
            "inventory.counts.manage",
            "inventory.transfers.create",
            "inventory.transfers.receive",
            "inventory.writeoffs.manage",
            "fulfillment.view",
            "fulfillment.manage",
            "hr.staff.manage",
        ],
    },
    "courier": {
        "name": "Dastavka (kuryer)",
        "capabilities": [
            "deliveries.view",
            "deliveries.manage",
        ],
    },
    "operator": {
        "name": "Operator",
        "capabilities": [
            "catalog.view",
            "inventory.view",
            "sales.view",
            "customers.view",
            "fulfillment.view",
            "fulfillment.verify",
        ],
    },
}

# Filial buxgalteri: buxgalter huquqlari, lekin faqat biriktirilgan nuqta(lar) ma'lumoti
ROLE_PRESETS["branch_accountant"] = {
    "name": "Filial buxgalteri",
    "capabilities": [
        c for c in ROLE_PRESETS["accountant"]["capabilities"] if c != "branches.view_all"
    ],
}

# Rahbarlar kimni qaysi rolga yollay oladi (filial rahbari — faqat o'z quyi xodimlarini)
BRANCH_STAFF_ROLES = ("storekeeper", "seller", "operator", "courier", "branch_accountant")


def assignable_role_codes(user) -> set[str] | None:
    """None — har qanday rol; aks holda ruxsat etilgan rol kodlari."""
    if user.has_capability("users.manage"):
        return None
    if user.has_capability("hr.manage"):
        return {code for code in ROLE_PRESETS if code != "owner"}
    if user.has_capability("hr.staff.manage"):
        return set(BRANCH_STAFF_ROLES)
    return set()
