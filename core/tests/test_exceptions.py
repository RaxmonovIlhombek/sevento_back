"""Yagona xato formati: Django xatolari, simplejwt, kutilmagan xatolar."""

import pytest
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from rest_framework import exceptions

from core.api.exceptions import exception_handler, flatten_validation_detail


def _error(exc):
    response = exception_handler(exc, {})
    return response.status_code, response.data["error"]


def test_django_http404_and_permission_denied():
    assert _error(Http404())[0] == 404
    assert _error(Http404())[1]["code"] == "not_found"
    status, error = _error(DjangoPermissionDenied())
    assert (status, error["code"]) == (403, "permission_denied")


def test_django_validation_error_with_fields_and_plain():
    status, error = _error(DjangoValidationError({"price": ["Manfiy bo'lmasin"]}))
    assert status == 400 and error["code"] == "validation_error"
    assert error["details"] == [
        {"field": "price", "code": "invalid", "message": "Manfiy bo'lmasin"}
    ]
    _, error = _error(DjangoValidationError("Umumiy xato"))
    assert error["details"][0]["field"] is None
    assert error["details"][0]["message"] == "Umumiy xato"


def test_simplejwt_style_detail_dict_uses_code():
    exc = exceptions.AuthenticationFailed({"detail": "Token yaroqsiz", "code": "token_not_valid"})
    status, error = _error(exc)
    assert status == 401 and error["code"] == "token_not_valid"


def test_throttled_keeps_retry_after_header():
    response = exception_handler(exceptions.Throttled(wait=30), {})
    assert response.status_code == 429
    assert response["Retry-After"] == "30"
    assert response.data["error"]["code"] == "throttled"


def test_unexpected_error_is_hidden_as_server_error(settings):
    settings.API_HANDLE_UNEXPECTED_ERRORS = True
    status, error = _error(RuntimeError("maxfiy ichki tafsilot"))
    assert status == 500 and error["code"] == "server_error"
    assert "maxfiy" not in error["message"]


def test_unexpected_error_reraised_in_debug(settings):
    settings.API_HANDLE_UNEXPECTED_ERRORS = False
    assert exception_handler(RuntimeError("x"), {}) is None


@pytest.mark.parametrize(
    ("detail", "fields"),
    [
        ({"items": [{"quantity": ["Musbat"]}, {}]}, ["items.0.quantity"]),
        ({"non_field_errors": ["Umumiy"]}, [None]),
        (["a", "b"], [None, None]),
    ],
)
def test_flatten_validation_detail_paths(detail, fields):
    assert [d["field"] for d in flatten_validation_detail(detail)] == fields
