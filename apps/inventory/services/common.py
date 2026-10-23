"""Hujjat qatorlari uchun umumiy tekshiruvlar (ko'chirish, inventarizatsiya, hisobdan chiqarish)."""

from decimal import Decimal

from core.exceptions import BusinessRuleError

from ..exceptions import InsufficientStock


def validation_error(message: str, details: list[dict]) -> BusinessRuleError:
    return BusinessRuleError(message, code="validation_error", status_code=400, details=details)


def precision_error(product, quantity: Decimal, field: str) -> dict | None:
    places = product.unit.decimal_places
    if quantity != quantity.quantize(Decimal(1).scaleb(-places)):
        return {
            "field": field,
            "code": "unit_precision",
            "message": f"«{product.unit.name}» uchun ko'pi bilan {places} xona kasr",
        }
    return None


def validate_lines(items: list[dict], *, quantity_key: str = "quantity") -> None:
    """Tovar faol, takrorlanmagan, miqdor birlik aniqligida. Xato bo'lsa 400 (qator bo'yicha)."""
    errors: list[dict] = []
    seen: set[int] = set()
    if not items:
        raise validation_error("Tovar qo'shilmagan", [{"field": "items", "code": "required"}])
    for index, item in enumerate(items):
        product = item["product"]
        if product.pk in seen:
            errors.append(
                {
                    "field": f"items.{index}.product",
                    "code": "duplicate_product",
                    "message": "Tovar takrorlangan",
                }
            )
        seen.add(product.pk)
        if not product.is_active:
            errors.append(
                {
                    "field": f"items.{index}.product",
                    "code": "product_inactive",
                    "message": "Tovar faol emas",
                }
            )
        quantity = item.get(quantity_key)
        if quantity is not None:
            error = precision_error(product, quantity, f"items.{index}.{quantity_key}")
            if error:
                errors.append(error)
    if errors:
        raise validation_error("Tovar qatorlarida xato bor", errors)


def line_insufficient(
    exc: InsufficientStock, product_name: str, position: int
) -> InsufficientStock:
    """FIFO chiqimdagi xatoni qator maydoniga bog'laydi (frontend qatorni belgilaydi)."""
    available = exc.details[0]["message"] if exc.details else ""
    return InsufficientStock(
        f"«{product_name}» omborda yetarli emas",
        details=[
            {
                "field": f"items.{position}.quantity",
                "code": "insufficient_stock",
                "message": available,
            }
        ],
    )
