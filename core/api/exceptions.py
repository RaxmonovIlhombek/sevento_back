"""Yagona xato formati:

{"error": {"code", "message", "details": [{"field", "code", "message"}], "request_id"}}
"""

import logging

from django.conf import settings
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.settings import api_settings
from rest_framework.views import exception_handler as drf_exception_handler

from ..context import get_context
from ..exceptions import BusinessRuleError

log = logging.getLogger("core.api")

MESSAGES_UZ = {
    "not_authenticated": "Avtorizatsiya talab qilinadi",
    "authentication_failed": "Login yoki parol noto'g'ri",
    "token_not_valid": "Token yaroqsiz yoki muddati tugagan",
    "user_inactive": "Foydalanuvchi faol emas",
    "user_not_found": "Foydalanuvchi topilmadi",
    "origin_not_allowed": "So'rov manbai ruxsat etilmagan",
    "permission_denied": "Ruxsat yo'q",
    "not_found": "Topilmadi",
    "method_not_allowed": "Bu metodga ruxsat yo'q",
    "not_acceptable": "So'ralgan format qo'llab-quvvatlanmaydi",
    "unsupported_media_type": "So'rov formati qo'llab-quvvatlanmaydi",
    "throttled": "Juda ko'p so'rov, birozdan keyin urinib ko'ring",
    "parse_error": "So'rov formati noto'g'ri",
    "validation_error": "Ma'lumotlar noto'g'ri",
    "server_error": "Server xatosi",
}


def error_response(
    *,
    status_code: int,
    code: str,
    message: str | None = None,
    details: list[dict] | None = None,
    headers: dict | None = None,
) -> Response:
    body = {
        "error": {
            "code": code,
            "message": message or MESSAGES_UZ.get(code, code),
            "details": details or [],
            "request_id": get_context().request_id,
        }
    }
    return Response(body, status=status_code, headers=headers)


def exception_handler(exc, context):
    if isinstance(exc, BusinessRuleError):
        return error_response(
            status_code=exc.status_code, code=exc.code, message=exc.message, details=exc.details
        )
    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, DjangoPermissionDenied):
        exc = exceptions.PermissionDenied()
    elif isinstance(exc, DjangoValidationError):
        exc = exceptions.ValidationError(detail=_django_validation_detail(exc))

    response = drf_exception_handler(exc, context)
    if response is None:
        if getattr(settings, "API_HANDLE_UNEXPECTED_ERRORS", not settings.DEBUG):
            log.exception("Kutilmagan xato", exc_info=exc)
            return error_response(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, code="server_error"
            )
        return None

    headers = {}
    if "Retry-After" in response:
        headers["Retry-After"] = response["Retry-After"]
    if "WWW-Authenticate" in response:
        headers["WWW-Authenticate"] = response["WWW-Authenticate"]
    if isinstance(exc, exceptions.AuthenticationFailed | exceptions.NotAuthenticated):
        # DRF autentifikatsiya klassi bo'lmagan view da 403 qaytaradi; API uchun doim 401
        response.status_code = status.HTTP_401_UNAUTHORIZED
        headers.setdefault("WWW-Authenticate", "Bearer")

    if isinstance(exc, exceptions.ValidationError):
        return error_response(
            status_code=response.status_code,
            code="validation_error",
            details=flatten_validation_detail(exc.detail),
            headers=headers,
        )

    code, message = _code_and_message(exc)
    return error_response(
        status_code=response.status_code, code=code, message=message, headers=headers
    )


def _code_and_message(exc: exceptions.APIException) -> tuple[str, str]:
    detail = exc.detail
    # simplejwt: {"detail": "...", "code": "token_not_valid", "messages": [...]}
    if isinstance(detail, dict) and "code" in detail:
        code = str(detail["code"])
        return code, MESSAGES_UZ.get(code, str(detail.get("detail", code)))
    if isinstance(detail, dict | list):
        code = exc.default_code
        return code, MESSAGES_UZ.get(code, exc.default_detail)
    code = getattr(detail, "code", None) or exc.default_code
    if code in MESSAGES_UZ:
        return code, MESSAGES_UZ[code]
    return code, str(detail)


def flatten_validation_detail(detail, prefix: str = "") -> list[dict]:
    """Ichma-ich serializer xatolarini tekis ro'yxatga aylantiradi: items.0.quantity."""
    items: list[dict] = []
    if isinstance(detail, dict):
        for key, value in detail.items():
            key = str(key)
            if key == api_settings.NON_FIELD_ERRORS_KEY:
                path = prefix
            else:
                path = f"{prefix}.{key}" if prefix else key
            items.extend(flatten_validation_detail(value, path))
    elif isinstance(detail, list):
        for index, value in enumerate(detail):
            if isinstance(value, dict | list):
                path = f"{prefix}.{index}" if prefix else str(index)
                items.extend(flatten_validation_detail(value, path))
            else:
                items.append(_detail_item(prefix, value))
    else:
        items.append(_detail_item(prefix, detail))
    return items


def _detail_item(field: str, value) -> dict:
    return {
        "field": field or None,
        "code": str(getattr(value, "code", "invalid")),
        "message": str(value),
    }


def _django_validation_detail(exc: DjangoValidationError):
    if hasattr(exc, "error_dict"):
        return {k: [str(m) for m in v] for k, v in exc.message_dict.items()}
    return {api_settings.NON_FIELD_ERRORS_KEY: list(exc.messages)}
