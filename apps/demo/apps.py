from django.apps import AppConfig


class DemoConfig(AppConfig):
    """Demo ma'lumotlar (`manage.py seed_demo`). Modeli yo'q; faqat boshqa app servislari orqali."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.demo"
    verbose_name = "Demo ma'lumotlar"
