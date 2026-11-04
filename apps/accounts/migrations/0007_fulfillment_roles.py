from django.db import migrations

from apps.accounts.capabilities import ROLE_PRESETS

NEW_FOR_OWNER = [
    "fulfillment.view",
    "fulfillment.pack",
    "fulfillment.verify",
    "fulfillment.manage",
    "hr.staff.manage",
]
# mavjud tizim rollariga qo'shiladigan huquqlar
EXTRA = {
    "storekeeper": ["fulfillment.pack"],
    "branch_manager": ["fulfillment.view", "fulfillment.manage", "hr.staff.manage"],
}
NEW_ROLE_CODES = ("operator", "branch_accountant")


def forwards(apps, schema_editor):
    Role = apps.get_model("accounts", "Role")
    for code, items in {"owner": NEW_FOR_OWNER, **EXTRA}.items():
        for role in Role.objects.filter(code=code, is_system=True):
            role.capabilities = sorted(set(role.capabilities or []) | set(items))
            role.save(update_fields=["capabilities"])
    for code in NEW_ROLE_CODES:
        preset = ROLE_PRESETS[code]
        Role.objects.get_or_create(
            code=code,
            defaults={
                "name": preset["name"],
                "capabilities": sorted(preset["capabilities"]),
                "is_system": True,
            },
        )


def backwards(apps, schema_editor):
    Role = apps.get_model("accounts", "Role")
    Role.objects.filter(code__in=NEW_ROLE_CODES, is_system=True, users__isnull=True).delete()
    for code, items in {"owner": NEW_FOR_OWNER, **EXTRA}.items():
        for role in Role.objects.filter(code=code, is_system=True):
            role.capabilities = [c for c in role.capabilities if c not in items]
            role.save(update_fields=["capabilities"])


class Migration(migrations.Migration):
    dependencies = [("accounts", "0006_hr_branch_courier_roles")]

    operations = [migrations.RunPython(forwards, backwards)]
