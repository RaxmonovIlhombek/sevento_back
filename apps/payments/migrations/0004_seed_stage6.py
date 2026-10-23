from django.db import migrations

MANUAL = {"deposit", "withdrawal", "expense"}


def seed(apps, schema_editor):
    CashFlowCategory = apps.get_model("payments", "CashFlowCategory")
    CashFlowCategory.objects.filter(code__in=MANUAL).update(is_manual=True)
    CashFlowCategory.objects.get_or_create(
        code="adjustment",
        defaults={"name": "Kassa farqi (smena yopilishi)", "direction": "both", "is_manual": False},
    )


class Migration(migrations.Migration):
    dependencies = [("payments", "0003_stage6")]

    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
