"""Idempotency-Key: takroriy POST (tarmoq uzilib qayta yuborilgan) ikkinchi hujjat yaratmaydi.

Ishlatish (ViewSet): class SaleViewSet(IdempotentCreateMixin, ...): ...
yoki har qanday handler ichida: return idempotent_call(request, lambda: ...).
"""

from collections.abc import Callable

from django.db import IntegrityError, transaction
from rest_framework.response import Response

from ..exceptions import DuplicateRequest
from ..models import IdempotencyRecord

HEADER = "Idempotency-Key"
MAX_KEY_LENGTH = 128


def idempotent_call(request, handler: Callable[[], Response]) -> Response:
    key = request.headers.get(HEADER)
    if not key:
        return handler()
    key = key[:MAX_KEY_LENGTH]
    method, path = request.method, request.path[:255]

    try:
        with transaction.atomic():
            record = IdempotencyRecord.objects.create(
                key=key, user=request.user, method=method, path=path
            )
    except IntegrityError:
        existing = IdempotencyRecord.objects.get(key=key, user=request.user)
        if existing.response_status is None:
            raise DuplicateRequest() from None
        if existing.method != method or existing.path != path:
            raise DuplicateRequest(
                "Bu Idempotency-Key boshqa so'rov uchun ishlatilgan", code="idempotency_key_reused"
            ) from None
        return Response(existing.response_body, status=existing.response_status)

    try:
        response = handler()
    except Exception:
        # Xato bo'lsa yozuv o'chiriladi — mijoz xuddi shu kalit bilan qayta urinishi mumkin
        IdempotencyRecord.objects.filter(pk=record.pk).delete()
        raise

    if 200 <= response.status_code < 300:
        IdempotencyRecord.objects.filter(pk=record.pk).update(
            response_status=response.status_code, response_body=response.data
        )
    else:
        IdempotencyRecord.objects.filter(pk=record.pk).delete()
    return response


class IdempotentCreateMixin:
    def create(self, request, *args, **kwargs):
        return idempotent_call(
            request, lambda: super(IdempotentCreateMixin, self).create(request, *args, **kwargs)
        )
