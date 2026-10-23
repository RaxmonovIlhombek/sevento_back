from decimal import Decimal

from .base import AllocationLine


class ByValue:
    """Qator qiymatiga (asosiy valyutada) proporsional. Hamma qiymat 0 bo'lsa — miqdor bo'yicha."""

    key = "by_value"

    def weights(self, lines: list[AllocationLine]) -> list[Decimal]:
        weights = [line.value_base for line in lines]
        if sum(weights, Decimal(0)) <= 0:
            return ByQuantity().weights(lines)
        return weights


class ByQuantity:
    """Miqdorga proporsional (bir xil o'lchamdagi tovarlar uchun)."""

    key = "by_quantity"

    def weights(self, lines: list[AllocationLine]) -> list[Decimal]:
        return [line.quantity for line in lines]
