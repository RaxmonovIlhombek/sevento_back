"""OpenAPI sxema sifati: har operatsiya teg, javob tavsifi bilan; yo'llar /api/v1/ ostida.

Frontend turlari (openapi-typescript) shu sxemadan generatsiya qilinadi — bo'sh javob sxemasi
frontend da `unknown` turiga aylanadi, shuning uchun 2xx javoblar tavsiflangan bo'lishi shart.
"""

import pytest
from drf_spectacular.generators import SchemaGenerator

METHODS = {"get", "post", "put", "patch", "delete"}
# Fayl (PDF/Excel) va 204 javoblari — sxemasiz bo'lishi tabiiy
BINARY_TYPES = {"application/pdf", "application/octet-stream"}


@pytest.fixture(scope="module")
def schema():
    return SchemaGenerator().get_schema(request=None, public=True)


def _operations(schema):
    for path, item in schema["paths"].items():
        for method, operation in item.items():
            if method in METHODS:
                yield path, method, operation


def test_paths_are_versioned(schema):
    assert schema["paths"]
    assert all(path.startswith("/api/v1/") for path in schema["paths"])


def test_every_operation_tagged_and_unique_id(schema):
    ids = []
    for path, method, operation in _operations(schema):
        assert operation.get("tags"), f"{method.upper()} {path}: teg yo'q"
        ids.append(operation["operationId"])
    assert len(ids) == len(set(ids))


def test_success_responses_have_schema(schema):
    missing = []
    for path, method, operation in _operations(schema):
        for code, response in operation["responses"].items():
            if not code.startswith("2") or code == "204":
                continue
            content = response.get("content", {})
            if not content or set(content) & BINARY_TYPES:
                if "description" not in response:
                    missing.append(f"{method.upper()} {path} {code}")
                continue
            if not any(c.get("schema") for c in content.values()):
                missing.append(f"{method.upper()} {path} {code}")
    assert not missing, "Javob sxemasi yo'q: " + ", ".join(missing)
