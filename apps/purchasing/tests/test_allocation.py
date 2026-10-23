from decimal import Decimal

import pytest

from apps.purchasing.allocation import AllocationLine, distribute, get_strategy

D = Decimal


def test_distribute_exact_sum_with_remainder_to_biggest():
    shares = distribute(D("100"), [D("1"), D("1"), D("1")])
    assert shares == [D("33.3334"), D("33.3333"), D("33.3333")]
    assert sum(shares) == D("100")

    shares = distribute(D("10"), [D("1"), D("2"), D("7")])
    assert shares == [D("1.0000"), D("2.0000"), D("7.0000")]


def test_distribute_edge_cases():
    assert distribute(D("5"), []) == []
    assert distribute(D("0"), [D("1"), D("2")]) == [D("0"), D("0")]
    # og'irlik yo'q → teng
    assert distribute(D("9"), [D("0"), D("0"), D("0")]) == [D("3.0000"), D("3.0000"), D("3.0000")]


@pytest.mark.parametrize("amount", ["0.0001", "1", "99.9999", "123456.7891"])
def test_distribute_sum_is_always_exact(amount):
    weights = [D("3.3"), D("0.7"), D("12.11"), D("5")]
    assert sum(distribute(D(amount), weights)) == D(amount)


def test_strategies():
    lines = [
        AllocationLine(quantity=D("10"), value_base=D("100")),
        AllocationLine(quantity=D("30"), value_base=D("100")),
    ]
    assert get_strategy("by_value").weights(lines) == [D("100"), D("100")]
    assert get_strategy("by_quantity").weights(lines) == [D("10"), D("30")]
    # hamma qiymat 0 (bepul tovar) → miqdor bo'yicha
    free = [
        AllocationLine(quantity=D("1"), value_base=D("0")),
        AllocationLine(quantity=D("3"), value_base=D("0")),
    ]
    assert get_strategy("by_value").weights(free) == [D("1"), D("3")]
    with pytest.raises(KeyError):
        get_strategy("by_weight")
