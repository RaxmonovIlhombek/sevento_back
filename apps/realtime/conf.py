from django.conf import settings

DEFAULTS = {
    "TICKET_TTL": 30,  # soniya — ticket shu vaqt ichida ishlatilishi kerak
    "AUTH_TIMEOUT": 5.0,  # ulanishdan keyin auth xabari kutiladigan vaqt
    "MAX_CONNECTIONS_PER_USER": 10,
    "USER_RECHECK_INTERVAL": 900,  # uzoq ulanishlarda foydalanuvchi hali faolligini tekshirish
    "ALLOWED_ORIGINS": ["*"],
}


def get(key: str):
    return getattr(settings, "REALTIME", {}).get(key, DEFAULTS[key])
