from django.db import migrations

SEED = [
    {"code": "USD", "name": "AQSH dollari", "symbol": "$", "decimal_places": 2, "sort_order": 0},
    {"code": "UZS", "name": "O'zbek so'mi", "symbol": "so'm", "decimal_places": 0, "sort_order": 1},
]


def seed(apps, schema_editor):
    Currency = apps.get_model("currency", "Currency")
    for row in SEED:
        Currency.objects.get_or_create(code=row["code"], defaults=row)


class Migration(migrations.Migration):
    dependencies = [("currency", "0001_initial")]

    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
