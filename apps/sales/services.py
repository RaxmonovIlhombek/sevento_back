"""Savdo: bitta tranzaksiyada narx → chegirma tekshiruvi → nasiya (limit) → FIFO chiqim →
to'lovlar → qaytim.

To'lov (naqd, karta, o'tkazma, bir nechta valyuta aralash) jamidan kam bo'lsa, qolgani mijoz
nomiga nasiya yoziladi (`sales.credit` huquqi va kredit limiti bilan).
"""

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_DOWN, ROUND_HALF_UP, ROUND_UP, Decimal

from django.db import transaction
from django.utils import timezone

from apps.catalog import selectors as catalog_selectors
from apps.currency import selectors as currency_selectors
from apps.inventory import services as inventory_services
from apps.inventory.exceptions import InsufficientStock
from apps.inventory.types import BatchAllocation, DocRef, MovementType
from apps.payments import services as payment_services
from apps.payments.types import PaymentDoc
from core import settings_service
from core.access import ensure_branch_access
from core.exceptions import BusinessRuleError, InvalidStatusTransition
from core.numbering import next_number

from . import events
from .exceptions import DiscountForbidden, PaymentInsufficient, TotalMismatch
from .models import Sale, SaleItem
from .pricing import line_gross, quantum, resolve_prices

DOC_TYPE = "sale"
NUMBER_PREFIX = "S"
MONEY_PLACES = Decimal("0.0001")


@dataclass
class PricedLine:
    index: int
    product: object
    quantity: Decimal
    unit_price: Decimal
    gross: Decimal
    discount: Decimal

    @property
    def line_total(self) -> Decimal:
        return self.gross - self.discount


def _validation_error(message: str, details: list[dict]) -> BusinessRuleError:
    return BusinessRuleError(message, code="validation_error", status_code=400, details=details)


def _price_lines(*, actor, branch, currency, price_type, items: list[dict]) -> list[PricedLine]:
    places = currency.decimal_places
    q = quantum(places)
    prices = resolve_prices(
        {item["product"].pk for item in items},
        price_type_code=price_type.code,
        currency_code=currency.code,
        decimal_places=places,
        branch_id=branch.pk,
    )
    errors: list[dict] = []
    lines: list[PricedLine] = []
    for index, item in enumerate(items):
        product, quantity = item["product"], item["quantity"]
        discount: Decimal = item.get("discount_amount") or Decimal(0)
        unit_places = product.unit.decimal_places
        if not product.is_active:
            errors.append(_err(index, "product", "product_inactive", "Tovar faol emas"))
        if quantity != quantity.quantize(quantum(unit_places)):
            errors.append(
                _err(
                    index,
                    "quantity",
                    "unit_precision",
                    f"«{product.unit.name}» uchun ko'pi bilan {unit_places} xona kasr",
                )
            )
        price = prices.get(product.pk)
        if price is None:
            errors.append(
                _err(
                    index, "product", "price_missing", f"«{product.name}» uchun narx belgilanmagan"
                )
            )
            continue
        gross = line_gross(quantity, price, places)
        if discount != discount.quantize(q):
            errors.append(
                _err(index, "discount_amount", "invalid", f"Ko'pi bilan {places} xona kasr")
            )
        elif discount > gross:
            errors.append(
                _err(index, "discount_amount", "discount_too_big", "Chegirma summadan katta")
            )
        lines.append(PricedLine(index, product, quantity, price, gross, discount))
    if errors:
        raise _validation_error("Savat qatorlarida xato bor", errors)
    _check_discounts(actor, lines)
    return lines


def _err(index: int, field: str, code: str, message: str) -> dict:
    return {"field": f"items.{index}.{field}", "code": code, "message": message}


def _check_discounts(actor, lines: list[PricedLine]) -> None:
    if not any(line.discount for line in lines):
        return
    if not actor.has_capability("sales.discount"):
        raise DiscountForbidden()
    if actor.has_capability("sales.discount.unlimited"):
        return
    limit = Decimal(settings_service.get("sales.max_seller_discount_percent"))
    errors = []
    for line in lines:
        if line.discount and line.gross and line.discount * 100 > line.gross * limit:
            errors.append(
                _err(
                    line.index,
                    "discount_amount",
                    "discount_limit",
                    f"Chegirma {limit.normalize():f}% dan oshmasin",
                )
            )
    if errors:
        raise BusinessRuleError(
            "Chegirma ruxsat etilgan chegaradan katta",
            code="discount_limit",
            status_code=400,
            details=errors,
        )


@dataclass
class PreparedPayment:
    method: object
    currency: object
    amount: Decimal
    in_sale_currency: Decimal


def _prepare_payments(payments: list[dict], sale_currency) -> list[PreparedPayment]:
    errors = []
    prepared = []
    for index, p in enumerate(payments):
        method, currency, amount = p["method"], p["currency"], p["amount"]
        if amount != amount.quantize(quantum(currency.decimal_places)):
            errors.append(
                {
                    "field": f"payments.{index}.amount",
                    "code": "invalid",
                    "message": f"{currency.code} uchun ko'pi bilan {currency.decimal_places} xona",
                }
            )
            continue
        if currency.pk == sale_currency.pk:
            converted = amount
        else:
            converted = (
                amount
                * currency_selectors.rate_value(currency.code)
                / currency_selectors.rate_value(sale_currency.code)
            ).quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)
        prepared.append(PreparedPayment(method, currency, amount, converted))
    if errors:
        raise _validation_error("To'lovlarda xato bor", errors)
    return prepared


def create_sale(
    *,
    actor,
    branch,
    currency,
    items: list[dict],
    payments: list[dict],
    price_type=None,
    customer=None,
    due_date: date | None = None,
    note: str = "",
    expected_total: Decimal | None = None,
) -> Sale:
    ensure_branch_access(actor, branch.pk)
    if not items:
        raise _validation_error("Savat bo'sh", [{"field": "items", "code": "required"}])
    price_type = price_type or catalog_selectors.default_price_type()
    if price_type is None:
        raise BusinessRuleError("Narx turi belgilanmagan", code="price_type_missing")
    places = currency.decimal_places

    lines = _price_lines(
        actor=actor, branch=branch, currency=currency, price_type=price_type, items=items
    )
    subtotal = sum((line.gross for line in lines), Decimal(0))
    discount_total = sum((line.discount for line in lines), Decimal(0))
    total = subtotal - discount_total
    if expected_total is not None and expected_total.quantize(quantum(places)) != total:
        raise TotalMismatch(
            details=[{"field": "expected_total", "code": "total_mismatch", "message": f"{total}"}]
        )

    prepared = _prepare_payments(payments, currency)
    paid_total = sum((p.in_sale_currency for p in prepared), Decimal(0))
    debt = Decimal(0)
    if paid_total < total and customer is not None:
        if not actor.has_capability("sales.credit"):
            raise BusinessRuleError(
                "Nasiyaga sotish huquqi yo'q", code="credit_forbidden", status_code=403
            )
        # qarz hech qachon kam yozilmaydi: kasr qoldiq yuqoriga yaxlitlanadi
        debt = (total - paid_total).quantize(quantum(places), rounding=ROUND_UP)
    elif paid_total < total:
        raise PaymentInsufficient(
            f"To'lov yetarli emas: yana {(total - paid_total).normalize():f} {currency.code}",
            details=[
                {
                    "field": "payments",
                    "code": "payment_insufficient",
                    "message": f"{(total - paid_total).normalize():f}",
                }
            ],
        )
    change = (paid_total - total).quantize(quantum(places), rounding=ROUND_DOWN)
    cash_paid = sum((p.in_sale_currency for p in prepared if p.method.is_cash), Decimal(0))
    if change > cash_paid:
        raise BusinessRuleError(
            "Ortiqcha summa faqat naqd to'lovda bo'lishi mumkin (qaytim naqd beriladi)",
            code="change_not_cash",
            status_code=400,
        )
    rate_to_base = currency_selectors.rate_to_base(currency.code)

    with transaction.atomic():
        now = timezone.now()
        sale = Sale.objects.create(
            number=next_number(
                doc_type=NUMBER_PREFIX, branch_id=branch.pk, branch_code=branch.code
            ),
            branch=branch,
            seller=actor,
            price_type=price_type,
            currency=currency,
            rate_to_base=rate_to_base,
            subtotal=subtotal,
            discount_total=discount_total,
            total=total,
            total_base=(total * rate_to_base).quantize(MONEY_PLACES, rounding=ROUND_HALF_UP),
            cost_base=Decimal(0),
            paid_total=paid_total,
            change_amount=change,
            customer=customer,
            debt_amount=debt,
            completed_at=now,
            note=note,
        )
        doc = PaymentDoc(type=DOC_TYPE, id=sale.pk, number=sale.number)
        if debt > 0:
            # limit tekshiruvi tovar chiqimidan oldin — rad etilsa og'ir ish qilinmaydi
            debt_row = payment_services.register_debt(
                actor=actor,
                customer=customer,
                branch=branch,
                currency=currency,
                amount=debt,
                doc=doc,
                due_date=due_date,
            )
            sale.due_date = debt_row.due_date
            sale.save(update_fields=["due_date"])
        sale_items = SaleItem.objects.bulk_create(
            [
                SaleItem(
                    sale=sale,
                    product=line.product,
                    position=line.index,
                    quantity=line.quantity,
                    unit_price=line.unit_price,
                    discount_amount=line.discount,
                    line_total=line.line_total,
                    cost_base=Decimal(0),
                )
                for line in lines
            ]
        )
        # Qulflar doim bir xil tartibda (tovar id bo'yicha) — parallel savdolarda deadlock bo'lmasin
        cost_total = Decimal(0)
        for item in sorted(sale_items, key=lambda i: (i.product_id, i.position)):
            try:
                result = inventory_services.issue_stock(
                    actor=actor,
                    branch_id=branch.pk,
                    product_id=item.product_id,
                    quantity=item.quantity,
                    movement_type=MovementType.SALE_OUT,
                    doc=DocRef(type=DOC_TYPE, id=sale.pk, number=sale.number, line_id=item.pk),
                )
            except InsufficientStock as exc:
                available = exc.details[0]["message"] if exc.details else ""
                raise InsufficientStock(
                    f"«{item.product.name}» omborda yetarli emas",
                    details=[
                        {
                            "field": f"items.{item.position}.quantity",
                            "code": "insufficient_stock",
                            "message": available,
                        }
                    ],
                ) from None
            item.cost_base = result.total_cost_base
            item.batch_allocations = [
                {
                    "batch_id": a.batch_id,
                    "quantity": str(a.quantity),
                    "unit_cost_base": str(a.unit_cost_base),
                }
                for a in result.allocations
            ]
            cost_total += result.total_cost_base
        SaleItem.objects.bulk_update(sale_items, ["cost_base", "batch_allocations"])

        for p in prepared:
            payment_services.receive_payment(
                actor=actor,
                branch=branch,
                method=p.method,
                currency=p.currency,
                amount=p.amount,
                doc=doc,
                customer=customer,
            )
        if change > 0:
            payment_services.give_change(
                actor=actor, branch=branch, currency=currency, amount=change, doc=doc
            )

        sale.cost_base = cost_total
        sale.save(update_fields=["cost_base", "updated_at"])
        events.SaleCompleted.publish_from(
            actor=actor,
            branch_id=branch.pk,
            sale_id=sale.pk,
            number=sale.number,
            seller_id=actor.pk,
            currency=currency.code,
            total=total,
            total_base=sale.total_base,
            cost_base=cost_total,
            discount_total=discount_total,
            items_count=len(sale_items),
            customer_id=customer.pk if customer else None,
            debt_amount=debt,
            payments=[
                {"method": p.method.code, "currency": p.currency.code, "amount": str(p.amount)}
                for p in prepared
            ],
        )
    return sale


def cancel_sale(*, actor, sale: Sale, reason: str) -> Sale:
    """Savdoni bekor qilish: tovar asl partiyalarga, to'lovlar teskari (naqd — kassadan)."""
    ensure_branch_access(actor, sale.branch_id)
    with transaction.atomic():
        sale = Sale.objects.select_for_update().get(pk=sale.pk)
        if sale.status != Sale.Status.COMPLETED:
            raise InvalidStatusTransition("Savdo allaqachon bekor qilingan")
        doc = DocRef(type=DOC_TYPE, id=sale.pk, number=sale.number)
        items = sorted(sale.items.all(), key=lambda i: (i.product_id, i.position))
        for item in items:
            inventory_services.restore_stock(
                actor=actor,
                branch_id=sale.branch_id,
                product_id=item.product_id,
                allocations=[
                    BatchAllocation(
                        batch_id=a["batch_id"],
                        quantity=Decimal(a["quantity"]),
                        unit_cost_base=Decimal(a["unit_cost_base"]),
                    )
                    for a in item.batch_allocations
                ],
                movement_type=MovementType.SALE_CANCEL,
                doc=DocRef(type=DOC_TYPE, id=sale.pk, number=sale.number, line_id=item.pk),
            )
        pay_doc = PaymentDoc(type=doc.type, id=doc.id, number=doc.number)
        # nasiya: to'lov qilingan bo'lsa bekor qilinmaydi (409 debt_has_payments)
        payment_services.cancel_document_debts(actor=actor, doc=pay_doc, reason=reason)
        payment_services.reverse_document_payments(actor=actor, doc=pay_doc, reason=reason)
        sale.status = Sale.Status.CANCELLED
        sale.cancelled_by = actor
        sale.cancelled_at = timezone.now()
        sale.cancel_reason = reason
        sale.save(
            update_fields=["status", "cancelled_by", "cancelled_at", "cancel_reason", "updated_at"]
        )
        events.SaleCancelled.publish_from(
            actor=actor,
            branch_id=sale.branch_id,
            sale_id=sale.pk,
            number=sale.number,
            total=sale.total,
            currency=sale.currency.code,
            reason=reason,
        )
    return sale
