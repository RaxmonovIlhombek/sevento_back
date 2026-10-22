import pytest
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


def test_health_ok_and_request_id_header():
    client = APIClient()
    response = client.get("/api/v1/health/", HTTP_X_REQUEST_ID="abc123")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": True, "redis": True}
    assert response["X-Request-ID"] == "abc123"


def test_request_id_generated_when_absent():
    response = APIClient().get("/api/v1/health/")
    assert len(response["X-Request-ID"]) == 16


def test_unauthenticated_error_format():
    response = APIClient().get("/api/v1/settings/")
    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "not_authenticated"
    assert body["error"]["message"] == "Avtorizatsiya talab qilinadi"
    assert body["error"]["details"] == []
    assert body["error"]["request_id"] == response["X-Request-ID"]


def test_invalid_token_error_format():
    client = APIClient(HTTP_AUTHORIZATION="Bearer not-a-token")
    response = client.get("/api/v1/settings/")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "token_not_valid"


def test_schema_and_docs_available():
    client = APIClient()
    assert client.get("/api/v1/schema/").status_code == 200
    assert client.get("/api/v1/docs/").status_code == 200


def test_flatten_validation_detail():
    from rest_framework.exceptions import ErrorDetail

    from core.api.exceptions import flatten_validation_detail

    detail = {
        "name": [ErrorDetail("Majburiy", code="required")],
        "items": [
            {},
            {"quantity": [ErrorDetail("Kam", code="min_value")]},
        ],
        "non_field_errors": [ErrorDetail("Umumiy", code="invalid")],
    }
    assert flatten_validation_detail(detail) == [
        {"field": "name", "code": "required", "message": "Majburiy"},
        {"field": "items.1.quantity", "code": "min_value", "message": "Kam"},
        {"field": None, "code": "invalid", "message": "Umumiy"},
    ]
