"""Davriy vazifalar jadvali MB da (django-celery-beat). Bu yerda faqat boshlang'ich qiymatlar.

Har app o'z vazifalarini settings_defs.py ichida register_periodic_task() bilan qo'shadi;
`bootstrap` buyrug'i ensure_periodic_tasks() ni chaqiradi (mavjudlarini o'zgartirmaydi —
rahbar admin panelda vaqtini o'zgartirgan bo'lsa saqlanib qoladi).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class PeriodicTaskDef:
    name: str
    task: str
    minute: str = "*"
    hour: str = "*"
    day_of_week: str = "*"
    day_of_month: str = "*"
    month_of_year: str = "*"
    description: str = ""


_TASKS: list[PeriodicTaskDef] = []


def register_periodic_task(*defs: PeriodicTaskDef) -> None:
    _TASKS.extend(defs)


def all_periodic_tasks() -> list[PeriodicTaskDef]:
    return list(_TASKS)


def ensure_periodic_tasks() -> int:
    from django_celery_beat.models import CrontabSchedule, PeriodicTask

    created = 0
    for d in _TASKS:
        if PeriodicTask.objects.filter(name=d.name).exists():
            continue
        schedule, _ = CrontabSchedule.objects.get_or_create(
            minute=d.minute,
            hour=d.hour,
            day_of_week=d.day_of_week,
            day_of_month=d.day_of_month,
            month_of_year=d.month_of_year,
            timezone="Asia/Tashkent",
        )
        PeriodicTask.objects.create(
            name=d.name, task=d.task, crontab=schedule, description=d.description
        )
        created += 1
    return created


register_periodic_task(
    PeriodicTaskDef(
        name="core: outbox qayta jo'natish",
        task="core.redispatch_outbox",
        minute="*",
        description="Jo'natilmay qolgan domen hodisalarini qayta tarqatadi",
    ),
    PeriodicTaskDef(
        name="core: tozalash",
        task="core.cleanup",
        minute="30",
        hour="3",
        description="Eski idempotency yozuvlari va tarqatilgan outbox ni o'chiradi",
    ),
)
