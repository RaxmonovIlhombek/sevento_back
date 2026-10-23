from core.scheduling import PeriodicTaskDef, register_periodic_task
from core.settings_registry import SettingDef, register

register(
    SettingDef(
        key="reports.sync_max_days",
        type="int",
        default=31,
        description="Davri shundan uzun hisobot fayli fonda tayyorlanadi (tayyor bo'lsa xabar)",
    ),
    SettingDef(
        key="reports.preview_row_limit",
        type="int",
        default=500,
        description="Ekranda ko'rsatiladigan qatorlar soni (fayl — hammasi)",
    ),
    SettingDef(
        key="reports.keep_days",
        type="int",
        default=7,
        description="Fonda tayyorlangan hisobot fayllari necha kun saqlanadi",
    ),
)

register_periodic_task(
    PeriodicTaskDef(
        name="reports: eski fayllarni tozalash",
        task="reports.cleanup_report_files",
        minute="20",
        hour="3",
        description="Saqlash muddati o'tgan hisobot fayllari o'chiriladi",
    )
)
