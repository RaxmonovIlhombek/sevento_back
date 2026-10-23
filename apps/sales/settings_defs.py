from core.settings_registry import SettingDef, register

register(
    SettingDef(
        key="sales.default_currency",
        type="str",
        default="UZS",
        description="Kassada (POS) savdo uchun boshlang'ich valyuta kodi",
    ),
    SettingDef(
        key="sales.convert_missing_price",
        type="bool",
        default=True,
        description="Tovarda savdo valyutasida narx bo'lmasa, boshqa valyutadagi narx joriy kurs "
        "bilan o'tkazilsinmi",
    ),
    SettingDef(
        key="sales.receipt_header",
        type="str",
        default="",
        description="Chek sarlavhasi (bo'sh — nuqta nomi)",
    ),
    SettingDef(
        key="sales.receipt_footer",
        type="str",
        default="Xaridingiz uchun rahmat!",
        description="Chek oxiridagi matn",
    ),
)
