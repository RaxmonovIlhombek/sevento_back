from .base import *  # noqa
from .base import REST_FRAMEWORK, env

DEBUG = True
ALLOWED_HOSTS = ["*"]

REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = [
    "rest_framework.renderers.JSONRenderer",
    "rest_framework.renderers.BrowsableAPIRenderer",
]

# Lokal http uchun cookie Secure bo'lmasligi mumkin
JWT_REFRESH_COOKIE = {
    "name": env("JWT_REFRESH_COOKIE_NAME", default="sevento_refresh"),
    "secure": env.bool("JWT_REFRESH_COOKIE_SECURE", default=False),
    "samesite": env("JWT_REFRESH_COOKIE_SAMESITE", default="Strict"),
    "path": "/api/v1/auth/",
}

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

REALTIME = {**REALTIME, "ALLOWED_ORIGINS": ["*"]}  # noqa: F405
