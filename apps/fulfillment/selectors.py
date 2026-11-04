from django.db.models import Count, Prefetch, Q, QuerySet

from apps.sales.models import SaleItem
from core.access import scope_queryset_to_user

from .models import Fulfillment

S = Fulfillment.Status


def fulfillments_queryset(user) -> QuerySet[Fulfillment]:
    """Foydalanuvchi ko'ra oladigan yetkazishlar: avval nuqta doirasi, keyin rol bo'yicha bosqich.

    - fulfillment.view  → o'z nuqtalaridagi hammasi (rahbar, operator-kuzatuvchi)
    - fulfillment.pack  → omborchi: kutayotgan va o'zi taxlagan (operator tekshirayotgan)lar
    - fulfillment.verify → operator: tekshirilayotgan va tayyorlar
    - deliveries.view   → kuryer: olinishi mumkin bo'lgan tayyorlar + o'zining yetkazishlari
    - sales.create      → sotuvchi: o'zi yuborgan buyurtmalar
    """
    qs = scope_queryset_to_user(Fulfillment.objects.all(), user, "branch").select_related(
        "sale", "sale__customer", "sale__currency", "branch", "packed_by", "verified_by", "courier"
    )
    if not user.has_capability("fulfillment.view"):
        cond = Q(pk__isnull=True)
        if user.has_capability("fulfillment.pack"):
            cond |= Q(status__in=[S.PENDING, S.PACKED])
        if user.has_capability("fulfillment.verify"):
            cond |= Q(status__in=[S.PACKED, S.READY])
        if user.has_capability("deliveries.view"):
            cond |= Q(status=S.READY) | Q(courier=user)
        if user.has_capability("sales.create"):
            cond |= Q(created_by=user)  # sotuvchi o'zi yuborganini kuzatadi
        qs = qs.filter(cond)
    return qs


def fulfillment_detail_queryset(user) -> QuerySet[Fulfillment]:
    return fulfillments_queryset(user).prefetch_related(
        Prefetch(
            "sale__items",
            queryset=SaleItem.objects.select_related("product", "product__unit"),
        ),
        "steps",
        "steps__actor",
    )


def status_counts(queryset: QuerySet[Fulfillment]) -> dict[str, int]:
    rows = queryset.order_by().values("status").annotate(n=Count("id"))
    counts = {value: 0 for value, _ in Fulfillment.Status.choices}
    counts.update({row["status"]: row["n"] for row in rows})
    return counts
