from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = "apps.accounts"
    label = "accounts"
    verbose_name = "Foydalanuvchilar"

    def ready(self):
        from . import schema  # noqa: F401 — drf-spectacular extension ro'yxatga olinadi
