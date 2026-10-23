"""Kirim: qoralama → qabul qilish (partiyalar, tannarx) → bekor qilish."""

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.inventory import selectors as inventory_selectors
from apps.inventory import services as inventory_services
from apps.inventory.types import DocRef, MovementType
from core.access import ensure_branch_access
from core.exceptions import BusinessRuleError, InvalidStatusTransition
from core.numbering import next_number

from . import events
from .costing import CostCalculation, calculate_costs
from .models import ExpenseType, Purchase, PurchaseExpense, PurchaseItem, Supplier

DOC_TYPE = "purchase"
NUMBER_PREFIX = "K"

TRANSITIONS = {
    Purchase.Status.DRAFT: {Purchase.Status.RECEIVED, Purchase.Status.CANCELLED},
    Purchase.Status.RECEIVED: {Purchase.Status.CANCELLED},
    Purchase.Status.CANCELLED: set(),
}


def _check_transition(purchase: Purchase, target: str) -> None:
    if target not in TRANSITIONS[purchase.status]:
        raise InvalidStatusTransition(
            f"Holat «{purchase.get_status_display()}» dan o'tib bo'lmaydi"
        )


def _changes(instance, fields: dict) -> dict:
    changes = {}
    for name, value in fields.items():
        old = getattr(instance, name)
        if old != value:
            changes[name] = {"old": getattr(old, "pk", old), "new": getattr(value, "pk", value)}
            setattr(instance, name, value)
    return changes


# --- yetkazib beruvchilar, xarajat turlari ---


def save_supplier(*, actor, supplier: Supplier | None = None, **fields) -> Supplier:
    with transaction.atomic():
        created = supplier is None
        if created:
            supplier = Supplier.objects.create(**fields)
            changes = {}
        else:
            changes = _changes(supplier, fields)
            supplier.save()
        if created or changes:
            events.SupplierSaved.publish_from(
                actor=actor,
                supplier_id=supplier.pk,
                supplier_name=supplier.name,
                created=created,
                changes=changes,
            )
    return supplier


def save_expense_type(*, actor, expense_type: ExpenseType | None = None, **fields) -> ExpenseType:
    with transaction.atomic():
        if expense_type is None:
            expense_type = ExpenseType.objects.create(**fields)
            changes = {}
        else:
            changes = _changes(expense_type, fields)
            expense_type.save()
        events.ExpenseTypeSaved.publish_from(
            actor=actor, expense_type_id=expense_type.pk, code=expense_type.code, changes=changes
        )
    return expense_type


# --- kirim hujjati ---


def _validate_items(items: list[dict]) -> None:
    errors = []
    for index, item in enumerate(items):
        product = item["product"]
        places = product.unit.decimal_places
        quantity: Decimal = item["quantity"]
        if not product.is_active:
            errors.append(
                {
                    "field": f"items.{index}.product",
                    "code": "product_inactive",
                    "message": "Tovar faol emas",
                }
            )
        if quantity != quantity.quantize(Decimal(1).scaleb(-places)):
            errors.append(
                {
                    "field": f"items.{index}.quantity",
                    "code": "unit_precision",
                    "message": f"«{product.unit.name}» uchun ko'pi bilan {places} xona kasr",
                }
            )
    if errors:
        raise BusinessRuleError(
            "Tovar qatorlarida xato bor", code="validation_error", status_code=400, details=errors
        )


def _write_lines(purchase: Purchase, items: list[dict] | None, expenses: list[dict] | None) -> None:
    if items is not None:
        _validate_items(items)
        purchase.items.all().delete()
        PurchaseItem.objects.bulk_create(
            [
                PurchaseItem(
                    purchase=purchase,
                    product=item["product"],
                    position=index,
                    quantity=item["quantity"],
                    unit_price=item["unit_price"],
                    line_total=(item["quantity"] * item["unit_price"]).quantize(Decimal("0.0001")),
                )
                for index, item in enumerate(items)
            ]
        )
    if expenses is not None:
        purchase.expenses.all().delete()
        PurchaseExpense.objects.bulk_create(
            [
                PurchaseExpense(
                    purchase=purchase,
                    expense_type=exp["expense_type"],
                    currency=exp["currency"],
                    amount=exp["amount"],
                    allocation_method=exp.get("allocation_method")
                    or exp["expense_type"].default_allocation,
                    note=exp.get("note", ""),
                )
                for exp in expenses
            ]
        )
    purchase.subtotal = sum((i.line_total for i in purchase.items.all()), Decimal(0))
    purchase.save(update_fields=["subtotal", "updated_at"])


def create_purchase(
    *,
    actor,
    branch,
    supplier,
    currency,
    items: list[dict],
    expenses: list[dict] | None = None,
    invoice_number: str = "",
    invoice_date=None,
    note: str = "",
) -> Purchase:
    ensure_branch_access(actor, branch.pk)
    with transaction.atomic():
        purchase = Purchase.objects.create(
            number=next_number(
                doc_type=NUMBER_PREFIX, branch_id=branch.pk, branch_code=branch.code
            ),
            branch=branch,
            supplier=supplier,
            currency=currency,
            invoice_number=invoice_number,
            invoice_date=invoice_date,
            note=note,
            created_by=actor,
        )
        _write_lines(purchase, items, expenses or [])
        events.PurchaseCreated.publish_from(
            actor=actor,
            branch_id=branch.pk,
            purchase_id=purchase.pk,
            number=purchase.number,
            supplier_id=supplier.pk,
        )
    return purchase


def update_purchase(
    *,
    actor,
    purchase: Purchase,
    items: list[dict] | None = None,
    expenses: list[dict] | None = None,
    **fields,
) -> Purchase:
    """Faqat qoralama. items/expenses berilsa — to'liq almashtiriladi."""
    ensure_branch_access(actor, purchase.branch_id)
    if "branch" in fields:
        ensure_branch_access(actor, fields["branch"].pk)
    with transaction.atomic():
        purchase = Purchase.objects.select_for_update().get(pk=purchase.pk)
        if purchase.status != Purchase.Status.DRAFT:
            raise InvalidStatusTransition("Faqat qoralamani tahrirlash mumkin")
        if "branch" in fields and fields["branch"].pk != purchase.branch_id:
            raise BusinessRuleError(
                "Kirim nuqtasini o'zgartirib bo'lmaydi (raqam nuqtaga bog'langan)",
                code="branch_locked",
            )
        fields.pop("branch", None)
        for name, value in fields.items():
            setattr(purchase, name, value)
        purchase.save()
        _write_lines(purchase, items, expenses)
    return purchase


def preview_costs(purchase: Purchase) -> CostCalculation:
    """Qoralama uchun joriy kurs bilan tannarx (saqlanmaydi)."""
    items = list(purchase.items.all())
    expenses = list(purchase.expenses.all())
    return calculate_costs(
        currency_code=purchase.currency.code,
        items=[(i.quantity, i.unit_price) for i in items],
        expenses=[(e.currency.code, e.amount, e.allocation_method) for e in expenses],
    )


def receive_purchase(*, actor, purchase: Purchase) -> Purchase:
    """Qabul qilish: kurs snapshot, xarajat taqsimoti, tannarx, partiyalar, harakatlar."""
    ensure_branch_access(actor, purchase.branch_id)
    with transaction.atomic():
        purchase = (
            Purchase.objects.select_for_update()
            .select_related("branch", "currency")
            .get(pk=purchase.pk)
        )
        _check_transition(purchase, Purchase.Status.RECEIVED)
        items = list(purchase.items.select_related("product"))
        expenses = list(purchase.expenses.select_related("currency"))
        if not items:
            raise BusinessRuleError("Kirimda tovar yo'q", code="purchase_empty")
        calc = calculate_costs(
            currency_code=purchase.currency.code,
            items=[(i.quantity, i.unit_price) for i in items],
            expenses=[(e.currency.code, e.amount, e.allocation_method) for e in expenses],
        )
        now = timezone.now()
        for expense, cost in zip(expenses, calc.expenses, strict=True):
            expense.rate_to_base = cost.rate_to_base
            expense.amount_base = cost.amount_base
        PurchaseExpense.objects.bulk_update(expenses, ["rate_to_base", "amount_base"])

        for item, line in zip(items, calc.lines, strict=True):
            item.line_total = line.line_total
            item.line_total_base = line.line_total_base
            item.allocated_expense_base = line.allocated_expense_base
            item.landed_unit_cost_base = line.landed_unit_cost_base
            inventory_services.receive_stock(
                actor=actor,
                branch_id=purchase.branch_id,
                product_id=item.product_id,
                quantity=item.quantity,
                unit_cost_base=line.landed_unit_cost_base,
                movement_type=MovementType.PURCHASE_IN,
                doc=DocRef(type=DOC_TYPE, id=purchase.pk, number=purchase.number, line_id=item.pk),
                received_at=now,
            )
        PurchaseItem.objects.bulk_update(
            items,
            ["line_total", "line_total_base", "allocated_expense_base", "landed_unit_cost_base"],
        )

        purchase.status = Purchase.Status.RECEIVED
        purchase.rate_to_base = calc.rate_to_base
        purchase.subtotal = calc.subtotal
        purchase.subtotal_base = calc.subtotal_base
        purchase.expenses_total_base = calc.expenses_total_base
        purchase.total_base = calc.total_base
        purchase.received_by = actor
        purchase.received_at = now
        purchase.save()

        events.PurchaseReceived.publish_from(
            actor=actor,
            branch_id=purchase.branch_id,
            purchase_id=purchase.pk,
            number=purchase.number,
            supplier_id=purchase.supplier_id,
            currency=purchase.currency.code,
            rate_to_base=calc.rate_to_base,
            subtotal=calc.subtotal,
            expenses_total_base=calc.expenses_total_base,
            total_base=calc.total_base,
            items=[
                {
                    "product_id": i.product_id,
                    "quantity": str(i.quantity),
                    "landed_unit_cost_base": str(i.landed_unit_cost_base),
                }
                for i in items
            ],
        )
    return purchase


def cancel_purchase(*, actor, purchase: Purchase, reason: str) -> Purchase:
    """Qoralama — shunchaki bekor. Qabul qilingan — partiyalardan chiqim bo'lmagan bo'lsagina."""
    ensure_branch_access(actor, purchase.branch_id)
    with transaction.atomic():
        purchase = Purchase.objects.select_for_update().get(pk=purchase.pk)
        _check_transition(purchase, Purchase.Status.CANCELLED)
        previous = purchase.status
        if previous == Purchase.Status.RECEIVED:
            inventory_services.reverse_receipt(
                actor=actor, doc_type=DOC_TYPE, doc_id=purchase.pk, doc_number=purchase.number
            )
        purchase.status = Purchase.Status.CANCELLED
        purchase.cancelled_by = actor
        purchase.cancelled_at = timezone.now()
        purchase.cancel_reason = reason
        purchase.save()
        events.PurchaseCancelled.publish_from(
            actor=actor,
            branch_id=purchase.branch_id,
            purchase_id=purchase.pk,
            number=purchase.number,
            previous_status=previous,
            reason=reason,
        )
    return purchase


def can_cancel(purchase: Purchase) -> bool:
    if purchase.status == Purchase.Status.DRAFT:
        return True
    if purchase.status == Purchase.Status.RECEIVED:
        return inventory_selectors.is_source_untouched(DOC_TYPE, purchase.pk)
    return False
