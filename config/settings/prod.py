from .base import *  # noqa
from .base import env

DEBUG = False

# Reverse proxy (Nginx) orqasida HTTPS
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True
SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = env.int("DJANGO_HSTS_SECONDS", default=60 * 60 * 24 * 30)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# prod da refresh cookie doim Secure
JWT_REFRESH_COOKIE = {
    "name": env("JWT_REFRESH_COOKIE_NAME", default="sevento_refresh"),
    "secure": True,
    "samesite": env("JWT_REFRESH_COOKIE_SAMESITE", default="Strict"),
    "path": "/api/v1/auth/",
}
