from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from typing import ClassVar, Protocol

PLACES = Decimal("0.0001")


@dataclass(frozen=True)
class AllocationLine:
    quantity: Decimal
    value_base: Decimal


class AllocationStrategy(Protocol):
    key: ClassVar[str]

    def weights(self, lines: list[AllocationLine]) -> list[Decimal]: ...


def distribute(amount: Decimal, weights: list[Decimal]) -> list[Decimal]:
    """Summani og'irliklarga proporsional bo'ladi; yaxlitlash qoldig'i eng katta ulushga.

    Natija yig'indisi doim aniq `amount` ga teng. Barcha og'irlik 0 bo'lsa — teng bo'linadi.
    """
    if not weights:
        return []
    if amount == 0:
        return [Decimal(0)] * len(weights)
    total = sum(weights, Decimal(0))
    if total <= 0:
        weights = [Decimal(1)] * len(weights)
        total = Decimal(len(weights))
    shares = [(amount * w / total).quantize(PLACES, rounding=ROUND_DOWN) for w in weights]
    remainder = amount - sum(shares, Decimal(0))
    if remainder:
        biggest = max(range(len(weights)), key=lambda i: (weights[i], -i))
        shares[biggest] += remainder
    return shares
