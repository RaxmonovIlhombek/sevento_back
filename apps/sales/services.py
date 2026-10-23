"""Savdo: bitta tranzaksiyada narx → chegirma tekshiruvi → nasiya (limit) → FIFO chiqim →
to'lovlar → qaytim.

To'lov (naqd, karta, o'tkazma, bir nechta valyuta aralash) jamidan kam bo'lsa, qolgani mijoz
nomiga nasiya yoziladi (`sales.credit` huquqi va kredit limiti bilan).
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_DOWN, ROUND_HALF_UP, ROUND_UP, Decimal

from django.db import transaction
from django.utils import timezone

from apps.catalog import selectors as catalog_selectors
from apps.currency import selectors as currency_selectors
from apps.inventory import services as inventory_services
from apps.inventory.exceptions import InsufficientStock
from apps.inventory.types import (
    BatchAllocation,
    DocRef,
    MovementType,
    allocations_from_json,
    allocations_to_json,
)
from apps.payments import services as payment_services
from apps.payments.types import PaymentDoc
from core import settings_service
from core.access import ensure_branch_access
from core.exceptions import BusinessRuleError, InvalidStatusTransition
from core.numbering import next_number

from . import events
from .exceptions import DiscountForbidden, PaymentInsufficient, SaleHasReturns, TotalMismatch
from .models import Sale, SaleItem, SaleReturn, SaleReturnItem
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
        if sale.returns.exists():
            raise SaleHasReturns()
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


# --- qaytarish ---

RETURN_DOC_TYPE = "sale_return"
RETURN_PREFIX = "Q"


def _return_amount(item: SaleItem, quantity: Decimal, places: int) -> Decimal:
    """Qator summasidan (chegirma ayirilgan) proporsional ulush.

    round(L·(r+q)/Q) − round(L·r/Q): hamma qaytarishlar yig'indisi aynan line_total ga teng.
    """
    q = quantum(places)

    def share(qty: Decimal) -> Decimal:
        return (item.line_total * qty / item.quantity).quantize(q, rounding=ROUND_HALF_UP)

    return share(item.returned_quantity + quantity) - share(item.returned_quantity)


def _return_allocations(item: SaleItem, quantity: Decimal) -> list[BatchAllocation]:
    """Savdo partiyalaridan hali qaytarilmagan qism — oxirgi partiyadan boshlab."""
    returned: dict[int, Decimal] = defaultdict(Decimal)
    for row in item.returns.all():
        for alloc in allocations_from_json(row.batch_allocations):
            returned[alloc.batch_id] += alloc.quantity
    result = []
    need = quantity
    for alloc in reversed(allocations_from_json(item.batch_allocations)):
        if need <= 0:
            break
        take = min(alloc.quantity - returned[alloc.batch_id], need)
        if take > 0:
            result.append(BatchAllocation(alloc.batch_id, take, alloc.unit_cost_base))
            need -= take
    if need > 0:  # returned_quantity tekshiruvidan keyin bo'lmasligi kerak
        raise BusinessRuleError("Qaytarish partiyalari mos kelmadi", code="return_allocation")
    return result


def _validate_return_lines(lines: list[dict], items: dict[int, SaleItem]) -> None:
    errors, seen = [], set()
    for index, line in enumerate(lines):
        item = items.get(line["sale_item"])
        field = f"items.{index}"
        if item is None:
            errors.append(_err(index, "sale_item", "not_in_sale", "Bu qator savdoda yo'q"))
            continue
        if item.pk in seen:
            errors.append(_err(index, "sale_item", "duplicate", "Qator takrorlangan"))
        seen.add(item.pk)
        quantity: Decimal = line["quantity"]
        available = item.quantity - item.returned_quantity
        places = item.product.unit.decimal_places
        if quantity > available:
            errors.append(
                {
                    "field": f"{field}.quantity",
                    "code": "exceeds_sold",
                    "message": f"Qaytarish mumkin: {available.normalize():f}",
                }
            )
        elif quantity != quantity.quantize(Decimal(1).scaleb(-places)):
            errors.append(
                _err(
                    index,
                    "quantity",
                    "unit_precision",
                    f"«{item.product.unit.name}» uchun ko'pi bilan {places} xona kasr",
                )
            )
    if errors:
        raise _validation_error("Qaytarish qatorlarida xato bor", errors)


def can_return_sale(actor, sale: Sale) -> bool:
    """Sotuvchi — faqat o'z savdosini; `sales.cancel` huquqi borlar — nuqtadagi istalganini."""
    return actor.has_capability("sales.returns.create") and (
        sale.seller_id == actor.pk or actor.has_capability("sales.cancel")
    )


def create_return(
    *, actor, sale: Sale, items: list[dict], reason: str, refund_method=None
) -> SaleReturn:
    """Qaytarish: tovar asl partiyalarga (tannarx saqlanadi) → summa avval savdo qarzidan
    ayiriladi → qolgani mijozga qaytariladi (default naqd; kassada yetmasa 409)."""
    ensure_branch_access(actor, sale.branch_id)
    if not items:
        raise _validation_error("Qaytariladigan tovar tanlanmagan", [{"field": "items"}])
    with transaction.atomic():
        sale = (
            Sale.objects.select_for_update(of=("self",))
            .select_related("branch", "currency", "customer")
            .get(pk=sale.pk)
        )
        if sale.status != Sale.Status.COMPLETED:
            raise InvalidStatusTransition("Bekor qilingan savdoni qaytarib bo'lmaydi")
        if not can_return_sale(actor, sale):
            raise BusinessRuleError(
                "Faqat o'z savdongizni qaytara olasiz", code="return_forbidden", status_code=403
            )
        sale_items = {
            i.pk: i
            for i in sale.items.select_for_update(of=("self",))
            .select_related("product", "product__unit")
            .prefetch_related("returns")
        }
        _validate_return_lines(items, sale_items)
        places = sale.currency.decimal_places
        sale_return = SaleReturn.objects.create(
            number=next_number(
                doc_type=RETURN_PREFIX, branch_id=sale.branch_id, branch_code=sale.branch.code
            ),
            sale=sale,
            branch=sale.branch,
            customer=sale.customer,
            currency=sale.currency,
            total=Decimal(0),
            total_base=Decimal(0),
            cost_base=Decimal(0),
            refund_method=refund_method,
            reason=reason,
            created_by=actor,
        )
        total = cost_total = Decimal(0)
        rows = []
        lines = sorted(items, key=lambda line: (sale_items[line["sale_item"]].product_id,))
        for line in lines:
            item = sale_items[line["sale_item"]]
            quantity = line["quantity"]
            amount = _return_amount(item, quantity, places)
            allocations = _return_allocations(item, quantity)
            row = SaleReturnItem.objects.create(
                sale_return=sale_return,
                sale_item=item,
                product=item.product,
                quantity=quantity,
                amount=amount,
                cost_base=Decimal(0),
                batch_allocations=allocations_to_json(allocations),
            )
            inventory_services.restore_stock(
                actor=actor,
                branch_id=sale.branch_id,
                product_id=item.product_id,
                allocations=allocations,
                movement_type=MovementType.SALE_RETURN_IN,
                doc=DocRef(
                    type=RETURN_DOC_TYPE,
                    id=sale_return.pk,
                    number=sale_return.number,
                    line_id=row.pk,
                ),
            )
            row.cost_base = sum(
                (
                    (a.quantity * a.unit_cost_base).quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)
                    for a in allocations
                ),
                Decimal(0),
            )
            row.save(update_fields=["cost_base"])
            rows.append(row)
            item.returned_quantity += quantity
            total += amount
            cost_total += row.cost_base
        SaleItem.objects.bulk_update(list(sale_items.values()), ["returned_quantity"])

        reduced = Decimal(0)
        if sale.debt_amount > 0 and total > 0:
            reduced = payment_services.reduce_document_debt(
                actor=actor,
                doc=PaymentDoc(type=DOC_TYPE, id=sale.pk, number=sale.number),
                currency=sale.currency,
                amount=total,
            )
        refund = total - reduced
        sale_return.refund_method = None
        if refund > 0:
            payment = payment_services.refund_to_customer(
                actor=actor,
                branch=sale.branch,
                currency=sale.currency,
                amount=refund,
                doc=PaymentDoc(type=RETURN_DOC_TYPE, id=sale_return.pk, number=sale_return.number),
                method=refund_method,
                customer=sale.customer,
                reason=f"{sale.number}: {reason}"[:255],
            )
            sale_return.refund_method = payment.method
        sale_return.total = total
        sale_return.total_base = (total * sale.rate_to_base).quantize(
            MONEY_PLACES, rounding=ROUND_HALF_UP
        )
        sale_return.cost_base = cost_total
        sale_return.debt_reduction = reduced
        sale_return.refund_amount = refund
        sale_return.save()

        sale.returned_total += total
        sale.returned_total_base += sale_return.total_base
        sale.returned_cost_base += cost_total
        sale.save(
            update_fields=[
                "returned_total",
                "returned_total_base",
                "returned_cost_base",
                "updated_at",
            ]
        )
        events.SaleReturnCompleted.publish_from(
            actor=actor,
            branch_id=sale.branch_id,
            return_id=sale_return.pk,
            number=sale_return.number,
            sale_id=sale.pk,
            sale_number=sale.number,
            currency=sale.currency.code,
            total=total,
            total_base=sale_return.total_base,
            cost_base=cost_total,
            debt_reduction=reduced,
            refund_amount=refund,
            items_count=len(rows),
            customer_id=sale.customer_id,
            reason=reason,
        )
    return sale_return
