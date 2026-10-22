import pytest
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory, force_authenticate

from core.api.idempotency import idempotent_call
from core.exceptions import DuplicateRequest
from core.models import IdempotencyRecord

pytestmark = pytest.mark.django_db


def _request(user, key=None, path="/api/v1/sales/"):
    factory = APIRequestFactory()
    headers = {"HTTP_IDEMPOTENCY_KEY": key} if key else {}
    request = factory.post(path, {}, format="json", **headers)
    force_authenticate(request, user=user)
    request.user = user
    return request


def test_without_header_calls_handler_every_time(django_user_model):
    user = django_user_model.objects.create_user(username="u1", password="x")
    calls = []

    def handler():
        calls.append(1)
        return Response({"n": len(calls)}, status=201)

    idempotent_call(_request(user), handler)
    idempotent_call(_request(user), handler)
    assert len(calls) == 2
    assert IdempotencyRecord.objects.count() == 0


def test_same_key_returns_stored_response(django_user_model):
    user = django_user_model.objects.create_user(username="u1", password="x")
    calls = []

    def handler():
        calls.append(1)
        return Response({"id": 10}, status=201)

    first = idempotent_call(_request(user, "k1"), handler)
    second = idempotent_call(_request(user, "k1"), handler)
    assert len(calls) == 1
    assert first.status_code == second.status_code == 201
    assert second.data == {"id": 10}


def test_same_key_different_user_is_independent(django_user_model):
    u1 = django_user_model.objects.create_user(username="u1", password="x")
    u2 = django_user_model.objects.create_user(username="u2", password="x")
    calls = []

    def handler():
        calls.append(1)
        return Response({}, status=201)

    idempotent_call(_request(u1, "k1"), handler)
    idempotent_call(_request(u2, "k1"), handler)
    assert len(calls) == 2


def test_key_reused_for_other_path_rejected(django_user_model):
    user = django_user_model.objects.create_user(username="u1", password="x")
    idempotent_call(_request(user, "k1"), lambda: Response({}, status=201))
    with pytest.raises(DuplicateRequest) as exc:
        idempotent_call(_request(user, "k1", path="/api/v1/payments/"), lambda: Response({}))
    assert exc.value.code == "idempotency_key_reused"


def test_handler_error_releases_key(django_user_model):
    user = django_user_model.objects.create_user(username="u1", password="x")

    def failing():
        raise RuntimeError("db down")

    with pytest.raises(RuntimeError):
        idempotent_call(_request(user, "k1"), failing)
    assert IdempotencyRecord.objects.count() == 0

    response = idempotent_call(_request(user, "k1"), lambda: Response({"ok": True}, status=201))
    assert response.data == {"ok": True}


def test_error_response_not_stored(django_user_model):
    user = django_user_model.objects.create_user(username="u1", password="x")
    idempotent_call(_request(user, "k1"), lambda: Response({"error": 1}, status=400))
    assert IdempotencyRecord.objects.count() == 0
