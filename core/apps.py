from django.apps import AppConfig
from django.utils.module_loading import autodiscover_modules


class CoreConfig(AppConfig):
    name = "core"
    verbose_name = "Yadro"

    def ready(self):
        # Har bir app ning subscribers.py va settings_defs.py fayllari shu yerda yuklanadi,
        # shunda hodisa obunachilari va sozlama ta'riflari ro'yxatga olinadi.
        autodiscover_modules("settings_defs")
        autodiscover_modules("subscribers")
