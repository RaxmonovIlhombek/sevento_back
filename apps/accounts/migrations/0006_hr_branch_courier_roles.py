from django.db import migrations

from apps.accounts.capabilities import ROLE_PRESETS

# Yangi huquqlar (0005 dan keyin qo'shilganlar) — rahbar (owner) ga beriladi
NEW_CAPABILITIES = [
    "hr.view", "hr.manage", "payroll.view", "payroll.manage",
    "accounting.view", "accounting.manage",
    "crm.view", "crm.manage",
    "manufacturing.view", "manufacturing.manage",
    "deliveries.view", "deliveries.manage",
]
NEW_ROLE_CODES = ("hr_manager", "branch_manager", "courier")


def forwards(apps, schema_editor):
    Role = apps.get_model("accounts", "Role")
    for role in Role.objects.filter(code="owner", is_system=True):
        merged = set(role.capabilities or []) | set(NEW_CAPABILITIES)
        role.capabilities = sorted(merged)
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
    for role in Role.objects.filter(code="owner", is_system=True):
        role.capabilities = [c for c in role.capabilities if c not in NEW_CAPABILITIES]
        role.save(update_fields=["capabilities"])


class Migration(migrations.Migration):
    dependencies = [("accounts", "0005_workflow_manage_capability")]

    operations = [migrations.RunPython(forwards, backwards)]
