import importlib
import pkgutil

from django.apps import AppConfig


class ReportsConfig(AppConfig):
    name = "apps.reports"
    label = "reports"
    verbose_name = "Hisobotlar"

    def ready(self):
        # Hisobot ta'riflari: definitions/ dagi har modul @register_report bilan o'zini qo'shadi —
        # yangi hisobot uchun faqat yangi fayl (mavjud kod o'zgarmaydi).
        from . import definitions

        for module in pkgutil.iter_modules(definitions.__path__):
            importlib.import_module(f"{definitions.__name__}.{module.name}")
