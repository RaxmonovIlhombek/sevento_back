from django.db import migrations

UNITS = [
    {"code": "dona", "name": "Dona", "decimal_places": 0},
    {"code": "kg", "name": "Kilogramm", "decimal_places": 3},
    {"code": "g", "name": "Gramm", "decimal_places": 0},
    {"code": "l", "name": "Litr", "decimal_places": 2},
    {"code": "m", "name": "Metr", "decimal_places": 2},
    {"code": "m2", "name": "Kvadrat metr", "decimal_places": 2},
    {"code": "pack", "name": "Qadoq", "decimal_places": 0},
]

PRICE_TYPES = [
    {"code": "retail", "name": "Chakana", "is_default": True, "sort_order": 0},
    {"code": "wholesale", "name": "Ulgurji", "is_default": False, "sort_order": 1},
]


def seed(apps, schema_editor):
    Unit = apps.get_model("catalog", "Unit")
    PriceType = apps.get_model("catalog", "PriceType")
    for row in UNITS:
        Unit.objects.get_or_create(code=row["code"], defaults=row)
    for row in PRICE_TYPES:
        PriceType.objects.get_or_create(code=row["code"], defaults=row)


class Migration(migrations.Migration):
    dependencies = [("catalog", "0001_initial")]

    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
