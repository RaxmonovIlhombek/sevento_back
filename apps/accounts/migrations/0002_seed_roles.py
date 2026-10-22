from django.db import migrations


def seed_roles(apps, schema_editor):
    from apps.accounts.capabilities import ROLE_PRESETS

    Role = apps.get_model("accounts", "Role")
    for code, preset in ROLE_PRESETS.items():
        Role.objects.get_or_create(
            code=code,
            defaults={
                "name": preset["name"],
                "capabilities": preset["capabilities"],
                "is_system": True,
            },
        )


class Migration(migrations.Migration):
    dependencies = [("accounts", "0001_initial")]

    operations = [migrations.RunPython(seed_roles, migrations.RunPython.noop)]
