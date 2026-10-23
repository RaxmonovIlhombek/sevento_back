from django.db import migrations

EXPENSE_TYPES = [
    {"code": "transport", "name": "Transport", "default_allocation": "by_value"},
    {"code": "customs", "name": "Bojxona", "default_allocation": "by_value"},
    {"code": "loading", "name": "Yuklash-tushirish", "default_allocation": "by_quantity"},
]


def seed(apps, schema_editor):
    ExpenseType = apps.get_model("purchasing", "ExpenseType")
    for row in EXPENSE_TYPES:
        ExpenseType.objects.get_or_create(code=row["code"], defaults=row)


class Migration(migrations.Migration):
    dependencies = [("purchasing", "0001_initial")]

    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
