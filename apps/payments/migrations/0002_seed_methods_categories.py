from django.db import migrations

METHODS = [
    {"code": "cash", "name": "Naqd pul", "provider": "manual", "is_cash": True, "sort_order": 1},
    {"code": "card", "name": "Plastik karta (terminal)", "provider": "manual", "sort_order": 2},
    {"code": "transfer", "name": "Bank o'tkazmasi", "provider": "manual", "sort_order": 3},
]

CATEGORIES = [
    {"code": "sale", "name": "Savdo", "direction": "both"},
    {"code": "refund", "name": "Pul qaytarish", "direction": "out"},
    {"code": "debt_payment", "name": "Qarz to'lovi", "direction": "in"},
    {"code": "expense", "name": "Xarajat", "direction": "out"},
    {"code": "deposit", "name": "Kassaga kiritish", "direction": "in"},
    {"code": "withdrawal", "name": "Kassadan olish (inkassatsiya)", "direction": "out"},
]


def seed(apps, schema_editor):
    PaymentMethod = apps.get_model("payments", "PaymentMethod")
    CashFlowCategory = apps.get_model("payments", "CashFlowCategory")
    for row in METHODS:
        PaymentMethod.objects.get_or_create(code=row["code"], defaults=row)
    for row in CATEGORIES:
        CashFlowCategory.objects.get_or_create(code=row["code"], defaults=row)


class Migration(migrations.Migration):
    dependencies = [("payments", "0001_initial")]

    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
