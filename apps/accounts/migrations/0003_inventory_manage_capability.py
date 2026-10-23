from django.db import migrations

NEW_CAPABILITY = "inventory.manage"
ROLES = ("owner", "storekeeper")


def add_capability(apps, schema_editor):
    """4-bosqich: yangi huquq mavjud tizim rollariga qo'shiladi (rahbar o'zgartirgan bo'lsa ham)."""
    Role = apps.get_model("accounts", "Role")
    for role in Role.objects.filter(code__in=ROLES, is_system=True):
        if NEW_CAPABILITY not in role.capabilities:
            role.capabilities = sorted([*role.capabilities, NEW_CAPABILITY])
            role.save(update_fields=["capabilities"])


def remove_capability(apps, schema_editor):
    Role = apps.get_model("accounts", "Role")
    for role in Role.objects.filter(capabilities__contains=[NEW_CAPABILITY]):
        role.capabilities = [c for c in role.capabilities if c != NEW_CAPABILITY]
        role.save(update_fields=["capabilities"])


class Migration(migrations.Migration):
    dependencies = [("accounts", "0002_seed_roles")]

    operations = [migrations.RunPython(add_capability, remove_capability)]
