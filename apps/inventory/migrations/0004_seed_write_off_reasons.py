from django.db import migrations

REASONS = [
    ("damaged", "Buzilgan / shikastlangan", False),
    ("expired", "Muddati o'tgan", False),
    ("lost", "Yo'qolgan", False),
    ("internal", "Ichki ehtiyoj", False),
    ("other", "Boshqa", False),
    # ko'chirish qabulida yetishmagan tovar — avtomatik hujjat
    ("transfer_shortage", "Ko'chirishda yetishmadi", True),
]


def seed(apps, schema_editor):
    WriteOffReason = apps.get_model("inventory", "WriteOffReason")
    for code, name, is_system in REASONS:
        WriteOffReason.objects.get_or_create(
            code=code, defaults={"name": name, "is_system": is_system}
        )


class Migration(migrations.Migration):
    dependencies = [("inventory", "0003_transfers_counts_writeoffs")]

    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
