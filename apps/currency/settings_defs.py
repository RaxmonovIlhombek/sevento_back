from core.scheduling import PeriodicTaskDef, register_periodic_task

register_periodic_task(
    PeriodicTaskDef(
        name="currency: kursni yangilash",
        task="currency.fetch_rates",
        minute="5",
        hour="9",
        description="Markaziy bank (yoki tanlangan manba) dan kunlik kurs; vaqti MB da o'zgaradi",
    )
)
