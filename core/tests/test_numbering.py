import pytest

from core.models import DocumentSequence
from core.numbering import next_number

pytestmark = pytest.mark.django_db


def test_sequential_per_type_branch_year():
    assert (
        next_number(doc_type="S", branch_id=1, branch_code="TSH1", year=2026) == "S-TSH1-26-000001"
    )
    assert (
        next_number(doc_type="S", branch_id=1, branch_code="TSH1", year=2026) == "S-TSH1-26-000002"
    )
    assert (
        next_number(doc_type="P", branch_id=1, branch_code="TSH1", year=2026) == "P-TSH1-26-000001"
    )
    assert (
        next_number(doc_type="S", branch_id=2, branch_code="SAM1", year=2026) == "S-SAM1-26-000001"
    )
    assert (
        next_number(doc_type="S", branch_id=1, branch_code="TSH1", year=2027) == "S-TSH1-27-000001"
    )
    assert DocumentSequence.objects.count() == 4


def test_default_year_is_current(settings):
    number = next_number(doc_type="S", branch_id=1, branch_code="TSH1")
    assert number.startswith("S-TSH1-")
    assert number.endswith("-000001")
