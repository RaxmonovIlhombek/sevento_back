from decimal import Decimal

from django.db.models import (
    BooleanField,
    Case,
    Count,
    DecimalField,
    ExpressionWrapper,
    F,
    OuterRef,
    Q,
    QuerySet,
    Subquery,
    Sum,
    Value,
    When,
)
from django.db.models.functions import Coalesce

from core import settings_service
from core.access import scope_queryset_to_user

from .models import (
    Batch,
    StockCount,
    StockCountItem,
    StockLevel,
    StockMovement,
    Transfer,
    WriteOff,
    WriteOffItem,
    WriteOffReason,
)
from .types import MovementType

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


def quantities(branch_id: int, product_ids) -> dict[int, Decimal]:
    """Bir nechta tovar qoldig'i bitta so'rovda (kassa qidiruvi uchun)."""
    rows = StockLevel.objects.filter(branch_id=branch_id, product_id__in=list(product_ids))
    return {row.product_id: row.quantity for row in rows.only("product_id", "quantity")}


def batches_for_source(source_type: str, source_id: int) -> QuerySet[Batch]:
    return Batch.objects.filter(source_type=source_type, source_id=source_id)


def is_source_untouched(source_type: str, source_id: int) -> bool:
    """Kirim partiyalaridan hali chiqim bo'lmaganmi (bekor qilish mumkinmi)."""
    return (
        not batches_for_source(source_type, source_id)
        .exclude(quantity_remaining=F("quantity_initial"))
        .exists()
    )


def latest_unit_cost(branch_id: int, product_id: int) -> Decimal:
    """Ortiqcha tovar tannarxi: shu nuqtadagi oxirgi partiya, bo'lmasa boshqa nuqtadagi, yoki 0."""
    batches = Batch.objects.filter(product_id=product_id).order_by("-received_at", "-id")
    batch = batches.filter(branch_id=branch_id).first() or batches.first()
    return batch.unit_cost_base if batch else Decimal(0)


# --- ko'chirish ---


def transfers_queryset(user) -> QuerySet[Transfer]:
    """Jo'natuvchi nuqtaniki — hammasi; qabul qiluvchiniki — qoralamadan tashqari."""
    qs = Transfer.objects.select_related(
        "from_branch", "to_branch", "created_by", "sent_by", "received_by", "cancelled_by"
    ).annotate(items_count=Count("items"))
    ids = user.accessible_branch_ids()
    if ids is None:
        return qs
    return qs.filter(
        Q(from_branch_id__in=ids) | (Q(to_branch_id__in=ids) & ~Q(status=Transfer.Status.DRAFT))
    )


def transfer_detail_queryset(user) -> QuerySet[Transfer]:
    return transfers_queryset(user).prefetch_related("items__product__unit", "write_offs")


def incoming_transfers_count(user) -> int:
    """Qabul qilinishi kutilayotganlar (menyu nishoni uchun)."""
    ids = user.accessible_branch_ids()
    qs = Transfer.objects.filter(status=Transfer.Status.SENT)
    if ids is not None:
        qs = qs.filter(to_branch_id__in=ids)
    return qs.count()


# --- inventarizatsiya ---


def counts_queryset(user) -> QuerySet[StockCount]:
    qs = StockCount.objects.select_related(
        "branch", "category", "created_by", "completed_by"
    ).annotate(
        items_count=Count("items", distinct=True),
        counted_count=Count(
            "items", filter=Q(items__counted_quantity__isnull=False), distinct=True
        ),
    )
    return scope_queryset_to_user(qs, user, "branch")


def count_items(count: StockCount) -> QuerySet[StockCountItem]:
    """Qatorlar + hozirgi qoldiq; diff_value — yakunlanganda haqiqiy farq, qoralamada taxminiy."""
    current = StockLevel.objects.filter(
        branch_id=count.branch_id, product_id=OuterRef("product_id")
    ).values("quantity")[:1]
    qs = count.items.select_related("product", "product__unit", "product__category").annotate(
        current_quantity=Coalesce(Subquery(current, output_field=QTY_FIELD), Value(Decimal(0)))
    )
    if count.status == StockCount.Status.DRAFT:
        return qs.annotate(
            diff_value=ExpressionWrapper(
                F("counted_quantity") - F("current_quantity"), output_field=QTY_FIELD
            )
        )
    return qs.annotate(diff_value=F("difference"))


# --- hisobdan chiqarish ---


def write_off_reasons(*, active_only: bool = False, manual_only: bool = False):
    qs = WriteOffReason.objects.all()
    if active_only:
        qs = qs.filter(is_active=True)
    if manual_only:
        qs = qs.filter(is_system=False)
    return qs


def write_offs_queryset(user) -> QuerySet[WriteOff]:
    qs = WriteOff.objects.select_related(
        "branch", "reason", "created_by", "cancelled_by", "transfer"
    ).annotate(items_count=Count("items"))
    return scope_queryset_to_user(qs, user, "branch")


def write_off_detail_queryset(user) -> QuerySet[WriteOff]:
    return write_offs_queryset(user).prefetch_related("items__product__unit")


# --- hisobotlar va dashboard uchun ---

TURNOVER_GROUPS = {
    "purchases": (MovementType.PURCHASE_IN, MovementType.PURCHASE_CANCEL),
    "sales": (
        MovementType.SALE_OUT,
        MovementType.SALE_CANCEL,
        MovementType.SALE_RETURN_IN,
        MovementType.SALE_RETURN_CANCEL,
    ),
    "transfers": (
        MovementType.TRANSFER_OUT,
        MovementType.TRANSFER_IN,
        MovementType.TRANSFER_CANCEL,
    ),
    "adjustments": (
        MovementType.COUNT_SURPLUS,
        MovementType.COUNT_SHORTAGE,
        MovementType.WRITE_OFF,
        MovementType.WRITE_OFF_CANCEL,
    ),
}


def stock_report(user, *, branch_id=None, category_ids=None, below_min=False, include_zero=False):
    qs = stock_queryset(user)
    if branch_id:
        qs = qs.filter(branch_id=branch_id)
    if category_ids:
        qs = qs.filter(product__category_id__in=category_ids)
    if below_min:
        qs = qs.filter(is_below_min=True)
    elif not include_zero:
        qs = qs.filter(quantity__gt=0)
    return qs.order_by("product__name", "branch__name")


def turnover(user, *, date_from, date_to, branch_id=None, category_ids=None) -> list[dict]:
    """Tovar aylanmasi: boshlang'ich, kirim/savdo/ko'chirish/tuzatish (ishorali), yakuniy."""
    qs = scope_queryset_to_user(StockMovement.objects.all(), user, "branch").filter(
        created_at__date__lte=date_to
    )
    if branch_id:
        qs = qs.filter(branch_id=branch_id)
    if category_ids:
        qs = qs.filter(product__category_id__in=category_ids)
    period = Q(created_at__date__gte=date_from)
    zero = Value(Decimal("0.000"))
    sums = {
        name: Coalesce(Sum("quantity", filter=period & Q(type__in=types)), zero)
        for name, types in TURNOVER_GROUPS.items()
    }
    rows = (
        qs.values(
            "product_id",
            "product__name",
            "product__sku",
            "product__unit__code",
            "product__unit__decimal_places",
        )
        .annotate(
            opening=Coalesce(Sum("quantity", filter=Q(created_at__date__lt=date_from)), zero),
            closing=Coalesce(Sum("quantity"), zero),
            moves=Count("id", filter=period),
            **sums,
        )
        .order_by("product__name")
    )
    return [r for r in rows if r["moves"] or r["opening"]]


def movements_report(user, *, date_from, date_to, branch_id=None, movement_type=None):
    qs = movements_queryset(user).filter(
        created_at__date__gte=date_from, created_at__date__lte=date_to
    )
    if branch_id:
        qs = qs.filter(branch_id=branch_id)
    if movement_type:
        qs = qs.filter(type=movement_type)
    return qs.order_by("created_at", "id")


def transfers_report(user, *, date_from, date_to, branch_id=None, status=None):
    qs = transfers_queryset(user).filter(
        created_at__date__gte=date_from, created_at__date__lte=date_to
    )
    if branch_id:
        qs = qs.filter(Q(from_branch_id=branch_id) | Q(to_branch_id=branch_id))
    if status:
        qs = qs.filter(status=status)
    return qs.order_by("created_at", "id")


def write_off_lines(user, *, date_from, date_to, branch_id=None, reason_id=None):
    qs = scope_queryset_to_user(
        WriteOffItem.objects.select_related(
            "write_off", "write_off__branch", "write_off__reason", "product", "product__unit"
        ),
        user,
        "write_off__branch",
    ).filter(
        write_off__status=WriteOff.Status.COMPLETED,
        write_off__completed_at__date__gte=date_from,
        write_off__completed_at__date__lte=date_to,
    )
    if branch_id:
        qs = qs.filter(write_off__branch_id=branch_id)
    if reason_id:
        qs = qs.filter(write_off__reason_id=reason_id)
    return qs.order_by("write_off__completed_at", "write_off_id", "position")


def low_stock_count(user, *, branch_id=None) -> int:
    qs = stock_queryset(user).filter(is_below_min=True)
    if branch_id:
        qs = qs.filter(branch_id=branch_id)
    return qs.count()


def stock_value_base(user, *, branch_id=None) -> Decimal:
    qs = scope_queryset_to_user(Batch.objects.filter(quantity_remaining__gt=0), user, "branch")
    if branch_id:
        qs = qs.filter(branch_id=branch_id)
    value = qs.aggregate(
        v=Sum(
            ExpressionWrapper(
                F("quantity_remaining") * F("unit_cost_base"), output_field=MONEY_FIELD
            )
        )
    )["v"]
    return value or Decimal(0)
