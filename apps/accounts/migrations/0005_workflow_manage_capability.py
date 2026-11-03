from django.db import migrations

NEW_CAPABILITY = "workflow.manage"
ROLES = ("owner",)


def add_capability(apps, schema_editor):
    """Tasdiqlash qoidalari va barcha so'rovlarni boshqarish huquqi — tizim rahbariga."""
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
    dependencies = [("accounts", "0004_user_avatar")]

    operations = [migrations.RunPython(add_capability, remove_capability)]
