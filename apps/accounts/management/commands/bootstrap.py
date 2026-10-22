"""Boshlang'ich holat: tizim rollari, davriy vazifalar, (MB bo'sh bo'lsa) rahbar foydalanuvchi.

Idempotent — har ishga tushirishda (docker entrypoint) chaqirish xavfsiz.
"""

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.accounts import services
from apps.accounts.models import Role, User
from core.scheduling import ensure_periodic_tasks


class Command(BaseCommand):
    help = "Rollar, davriy vazifalar va boshlang'ich rahbarni yaratadi (idempotent)"

    def handle(self, *args, **options):
        roles = services.ensure_preset_roles()
        self.stdout.write(f"Rollar: {roles} ta yaratildi")

        tasks = ensure_periodic_tasks()
        self.stdout.write(f"Davriy vazifalar: {tasks} ta yaratildi")

        cfg = settings.BOOTSTRAP_ADMIN
        if User.objects.exists():
            self.stdout.write("Foydalanuvchilar mavjud — rahbar yaratilmadi")
            return
        if not cfg["username"] or not cfg["password"]:
            self.stdout.write(
                self.style.WARNING(
                    "BOOTSTRAP_ADMIN_USERNAME / PASSWORD berilmagan — rahbar yaratilmadi"
                )
            )
            return
        user = User.objects.create_superuser(
            username=cfg["username"],
            password=cfg["password"],
            full_name=cfg["full_name"],
            role=Role.objects.get(code="owner"),
        )
        self.stdout.write(self.style.SUCCESS(f"Rahbar yaratildi: {user.username}"))
