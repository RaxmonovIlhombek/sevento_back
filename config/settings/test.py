import os

os.environ.setdefault("DJANGO_SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("DATABASE_URL", "postgres://sevento:sevento@127.0.0.1:5432/sevento")
os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:6379/1")

from .base import *  # noqa
from .base import REST_FRAMEWORK

DEBUG = False
ALLOWED_HOSTS = ["*"]

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Celery vazifalari testda darhol, shu jarayonda bajariladi
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {"login": "1000/min", "ws_ticket": "1000/min"}

JWT_REFRESH_COOKIE = {
    "name": "sevento_refresh",
    "secure": False,
    "samesite": "Strict",
    "path": "/api/v1/auth/",
}

REALTIME = {
    "TICKET_TTL": 30,
    "AUTH_TIMEOUT": 0.3,
    "MAX_CONNECTIONS_PER_USER": 10,
    "USER_RECHECK_INTERVAL": 900,
    "ALLOWED_ORIGINS": ["*"],
}

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
