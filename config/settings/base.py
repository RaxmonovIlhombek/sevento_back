"""Umumiy sozlamalar. Muhitga bog'liq qiymatlar faqat .env / muhit o'zgaruvchilaridan."""

from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
if (BASE_DIR / ".env").exists():
    environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = False
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

# Brauzer kelib chiqishi (Origin) ro'yxati: cookie bilan ishlaydigan auth endpointlari
# va Django CSRF shu ro'yxatni tekshiradi.
CSRF_TRUSTED_ORIGINS = env.list(
    "DJANGO_TRUSTED_ORIGINS",
    default=["http://localhost:5173", "http://localhost:3000"],
)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # uchinchi tomon
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "drf_spectacular",
    "django_filters",
    "django_celery_beat",
    "channels",
    # loyiha
    "core",
    "apps.accounts",
    "apps.branches",
    "apps.audit",
    "apps.realtime",
    "apps.currency",
    "apps.catalog",
    "apps.inventory",
    "apps.purchasing",
    "apps.payments",
    "apps.sales",
    "apps.reports",
    "apps.demo",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "core.middleware.RequestContextMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# --- Ma'lumotlar bazasi (faqat PostgreSQL) ---
DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Redis: kesh, channel layer, Celery ---
REDIS_URL = env("REDIS_URL", default="redis://127.0.0.1:6379/0")

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        "KEY_PREFIX": "sevento",
    }
}

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [REDIS_URL]},
    }
}

CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_TIMEZONE = "Asia/Tashkent"
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 60 * 10
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

# --- Autentifikatsiya ---
AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- Til va vaqt ---
LANGUAGE_CODE = "uz"
TIME_ZONE = "Asia/Tashkent"
USE_I18N = True
USE_TZ = True

# --- Statik va media ---
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"] if (BASE_DIR / "static").exists() else []
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
MEDIA_URL = "/media/"
MEDIA_ROOT = env("MEDIA_ROOT", default=str(BASE_DIR / "media"))

# --- DRF ---
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.accounts.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
    ],
    "DEFAULT_PAGINATION_CLASS": "core.api.pagination.StandardPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "login": env("THROTTLE_LOGIN", default="10/min"),
        "ws_ticket": env("THROTTLE_WS_TICKET", default="60/min"),
    },
    "EXCEPTION_HANDLER": "core.api.exceptions.exception_handler",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DATETIME_FORMAT": "iso-8601",
    "COERCE_DECIMAL_TO_STRING": True,
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env.int("JWT_ACCESS_MINUTES", default=15)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env.int("JWT_REFRESH_DAYS", default=7)),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": False,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

# Refresh token cookie (faqat auth endpointlariga yuboriladi)
JWT_REFRESH_COOKIE = {
    "name": env("JWT_REFRESH_COOKIE_NAME", default="sevento_refresh"),
    "secure": env.bool("JWT_REFRESH_COOKIE_SECURE", default=True),
    "samesite": env("JWT_REFRESH_COOKIE_SAMESITE", default="Strict"),
    "path": "/api/v1/auth/",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Sevento API",
    "DESCRIPTION": "Savdo, ombor, nasiya va kassa hisobi tizimi. Endpointlar /api/v1/ ostida.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": r"/api/v1",
    "COMPONENT_SPLIT_REQUEST": True,
    "SORT_OPERATIONS": True,
    "ENUM_NAME_OVERRIDES": {
        "AllocationMethodEnum": "apps.purchasing.models.AllocationMethod",
        "MovementTypeEnum": "apps.inventory.types.MovementType",
        "PurchaseStatusEnum": "apps.purchasing.models.Purchase.Status",
        "PaymentKindEnum": "apps.payments.types.PaymentKind",
        "PaymentDirectionEnum": "apps.payments.types.Direction",
        "PaymentStatusEnum": "apps.payments.models.Payment.Status",
        "SaleStatusEnum": "apps.sales.models.Sale.Status",
        "TransferStatusEnum": "apps.inventory.models.Transfer.Status",
        "StockCountStatusEnum": "apps.inventory.models.StockCount.Status",
        "ReportJobStatusEnum": "apps.reports.models.ReportJob.Status",
    },
    "POSTPROCESSING_HOOKS": [
        "drf_spectacular.hooks.postprocess_schema_enums",
    ],
}

# --- Valyuta kursi manbai ---
CURRENCY_CBU_URL = env("CURRENCY_CBU_URL", default="https://cbu.uz/uz/arkhiv-kursov-valyut/json/")

# --- WebSocket (apps.realtime) ---
REALTIME = {
    "TICKET_TTL": env.int("REALTIME_TICKET_TTL", default=30),
    "AUTH_TIMEOUT": env.float("REALTIME_AUTH_TIMEOUT", default=5.0),
    "MAX_CONNECTIONS_PER_USER": env.int("REALTIME_MAX_CONNECTIONS_PER_USER", default=10),
    "USER_RECHECK_INTERVAL": env.int("REALTIME_USER_RECHECK_INTERVAL", default=900),
    # Brauzer Origin ro'yxati (Tauri oynasi ham). "*" — hammasi (faqat dev)
    "ALLOWED_ORIGINS": env.list(
        "REALTIME_ALLOWED_ORIGINS",
        default=CSRF_TRUSTED_ORIGINS + ["tauri://localhost", "http://tauri.localhost"],
    ),
}

# --- Boshlang'ich foydalanuvchi (bootstrap buyrug'i) ---
BOOTSTRAP_ADMIN = {
    "username": env("BOOTSTRAP_ADMIN_USERNAME", default=""),
    "password": env("BOOTSTRAP_ADMIN_PASSWORD", default=""),
    "full_name": env("BOOTSTRAP_ADMIN_FULL_NAME", default="Rahbar"),
}

# --- Loglar ---
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "default"},
    },
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
    "loggers": {
        "django.request": {"level": "WARNING"},
        "core.events": {"level": "INFO"},
        # PDF (WeasyPrint) shrift kutubxonasi DEBUG da juda ko'p yozadi
        "fontTools": {"level": "WARNING"},
        "weasyprint": {"level": "WARNING"},
    },
}
