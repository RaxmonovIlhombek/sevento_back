from core.scheduling import PeriodicTaskDef, register_periodic_task
from core.settings_registry import SettingDef, register

register(
    SettingDef(
        key="cashbox.require_open_shift",
        type="bool",
        default=False,
        description="Naqd pul harakati (savdo, to'lov, qo'lda yozuv) faqat ochiq smenada",
    ),
)

register_periodic_task(
    PeriodicTaskDef(
        name="payments: muddati o'tgan qarzlar",
        task="payments.detect_overdue_debts",
        minute="5",
        hour="8",
        description="Muddati o'tgan qarzlar — buxgalterga ogohlantirish (har qarz uchun bir marta)",
    )
)
