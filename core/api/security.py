"""Cookie bilan ishlaydigan endpointlar uchun Origin tekshiruvi (CSRF ga qarshi qo'shimcha qatlam).

Refresh cookie SameSite=Strict bo'lgani uchun begona saytdan avtomatik yuborilmaydi; bu tekshiruv
sozlama xato bo'lsa ham (masalan Lax) himoya qiladi. Origin/Referer bo'lmasa (brauzer bo'lmagan
mijoz) o'tkaziladi — unda cookie ham avtomatik ketmaydi.
"""

from urllib.parse import urlsplit

from django.conf import settings
from rest_framework.exceptions import PermissionDenied


def _allowed_origins(request) -> set[str]:
    allowed = set(settings.CSRF_TRUSTED_ORIGINS)
    scheme = "https" if request.is_secure() else "http"
    allowed.add(f"{scheme}://{request.get_host()}")
    return allowed


def check_origin(request) -> None:
    origin = request.headers.get("Origin")
    if not origin:
        referer = request.headers.get("Referer")
        if not referer:
            return
        parts = urlsplit(referer)
        origin = f"{parts.scheme}://{parts.netloc}"
    if origin == "null" or origin not in _allowed_origins(request):
        raise PermissionDenied(code="origin_not_allowed")
