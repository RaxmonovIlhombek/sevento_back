from decimal import Decimal

from django.db.models import (
    BooleanField,
    Case,
    DecimalField,
    ExpressionWrapper,
    F,
    OuterRef,
    QuerySet,
    Subquery,
    Sum,
    Value,
    When,
)
from django.db.models.functions import Coalesce

from core import settings_service
from core.access import scope_queryset_to_user

from .models import Batch, StockLevel, StockMovement

QTY_FIELD = DecimalField(max_digits=14, decimal_places=3)
MONEY_FIELD = DecimalField(max_digits=24, decimal_places=4)


def _default_min() -> Decimal:
    return Decimal(settings_service.get("inventory.default_min_quantity"))


def stock_queryset(user) -> QuerySet[StockLevel]:
    """Qoldiqlar: effektiv minimal qoldiq, minimaldan pastligi va qiymati (tannarx bo'yicha)."""
    value_sq = (
        Batch.objects.filter(
            branch_id=OuterRef("branch_id"),
            product_id=OuterRef("product_id"),
            quantity_remaining__gt=0,
        )
        .values("branch_id", "product_id")
        .annotate(
            v=Sum(
                ExpressionWrapper(
                    F("quantity_remaining") * F("unit_cost_base"), output_field=MONEY_FIELD
                )
            )
        )
        .values("v")
    )
    effective_min = Coalesce(
        F("min_quantity"), F("product__min_quantity"), Value(_default_min()), output_field=QTY_FIELD
    )
    qs = (
        StockLevel.objects.select_related("branch", "product", "product__unit", "product__category")
        .annotate(
            effective_min=effective_min,
            value_base=Coalesce(Subquery(value_sq, output_field=MONEY_FIELD), Value(Decimal(0))),
        )
        .annotate(
            is_below_min=Case(
                When(effective_min__gt=0, quantity__lt=F("effective_min"), then=Value(True)),
                default=Value(False),
                output_field=BooleanField(),
            )
        )
    )
    return scope_queryset_to_user(qs, user, "branch")


def batches_queryset(user) -> QuerySet[Batch]:
    qs = Batch.objects.select_related("branch", "product", "product__unit")
    return scope_queryset_to_user(qs, user, "branch")


def movements_queryset(user) -> QuerySet[StockMovement]:
    qs = StockMovement.objects.select_related(
        "branch", "product", "product__unit", "created_by", "batch"
    )
    return scope_queryset_to_user(qs, user, "branch")


def get_quantity(branch_id: int, product_id: int) -> Decimal:
    level = StockLevel.objects.filter(branch_id=branch_id, product_id=product_id).first()
    return level.quantity if level else Decimal(0)


def batches_for_source(source_type: str, source_id: int) -> QuerySet[Batch]:
    return Batch.objects.filter(source_type=source_type, source_id=source_id)


def is_source_untouched(source_type: str, source_id: int) -> bool:
    """Kirim partiyalaridan hali chiqim bo'lmaganmi (bekor qilish mumkinmi)."""
    return (
        not batches_for_source(source_type, source_id)
        .exclude(quantity_remaining=F("quantity_initial"))
        .exists()
    )
