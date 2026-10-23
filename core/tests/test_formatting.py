from decimal import Decimal

from core.formatting import NBSP, format_number


def test_uzbek_number_format():
    assert format_number(Decimal("12650.45")) == f"12{NBSP}650,45"
    assert format_number(Decimal("142500"), 0) == f"142{NBSP}500"
    assert format_number(Decimal("1.5"), 3) == "1,500"
    assert format_number(Decimal("1.5"), 3, trim=True) == "1,5"
    assert format_number(Decimal("-1234567.891"), 2) == f"-1{NBSP}234{NBSP}567,89"
    assert format_number(None) == "—"
    assert format_number(Decimal("0.004"), 2) == "0,00"
