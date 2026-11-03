from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.accounts.models import User
from apps.notifications.models import Notification

from .models import ApprovalInstance, ApprovalRule, ApprovalStep
from .types import REQUEST_TYPES

Status = ApprovalInstance.Status
Decision = ApprovalStep.Decision


def matching_rules(*, entity_type: str, amount: Decimal, branch_id: int | None):
    """So'rovga mos faol qoidalar: tur, summa oralig'i va nuqta bo'yicha (tartib: sequence)."""
    qs = ApprovalRule.objects.filter(
        entity_type=entity_type, is_active=True, min_amount__lte=amount
    ).filter(Q(max_amount__isnull=True) | Q(max_amount__gte=amount))
    qs = qs.filter(Q(branch__isnull=True) | Q(branch_id=branch_id))
    return qs.select_related("approver").order_by("sequence", "id")


def current_step(instance: ApprovalInstance) -> ApprovalStep | None:
    """Hozir navbat kimda: birinchi kutilayotgan bosqich."""
    for step in instance.steps.all():
        if step.decision == Decision.PENDING:
            return step
    return None


def _notify(user, *, title, message="", kind=Notification.Type.INFO):
    Notification.objects.create(
        user=user,
        title=title,
        message=message,
        notification_type=kind,
        link="/workflow",
        source="workflow",
    )


@transaction.atomic
def create_request(
    *,
    actor: User,
    entity_type: str,
    title: str,
    amount: Decimal,
    branch_id: int | None,
    notes: str = "",
) -> ApprovalInstance:
    if entity_type not in REQUEST_TYPES:
        raise ValidationError({"entity_type": "Noma'lum so'rov turi"})
    rules = [r for r in matching_rules(entity_type=entity_type, amount=amount, branch_id=branch_id)]
    if not rules:
        raise ValidationError(
            "Bu tur va summa uchun tasdiqlovchi belgilanmagan. "
            "Rahbar Qoidalar bo'limida qoida qo'shishi kerak."
        )
    instance = ApprovalInstance.objects.create(
        entity_type=entity_type,
        title=title,
        requested_by=actor,
        branch_id=branch_id,
        amount=amount,
        notes=notes,
    )
    # So'rovchi o'zi tasdiqlovchi bo'lsa, o'z bosqichi o'tkazib yuboriladi
    steps = [r for r in rules if r.approver_id != actor.id]
    for i, rule in enumerate(steps, start=1):
        ApprovalStep.objects.create(instance=instance, approver=rule.approver, sequence=i)
    if not steps:
        instance.status = Status.APPROVED
        instance.decided_at = timezone.now()
        instance.save(update_fields=["status", "decided_at", "updated_at"])
    else:
        first = instance.steps.first()
        _notify(
            first.approver,
            title="Yangi tasdiqlash so'rovi",
            message=f"{actor.full_name}: {title} ({REQUEST_TYPES[entity_type]})",
            kind=Notification.Type.WARNING,
        )
    return instance


@transaction.atomic
def decide(
    *, actor: User, instance: ApprovalInstance, approve: bool, comment: str = ""
) -> ApprovalInstance:
    instance = ApprovalInstance.objects.select_for_update().get(pk=instance.pk)
    if instance.status != Status.PENDING:
        raise ValidationError("Bu so'rov allaqachon yakunlangan")
    step = current_step(instance)
    if step is None or step.approver_id != actor.id:
        raise PermissionDenied("Hozir bu so'rovni hal qilish navbati sizda emas")

    now = timezone.now()
    step.decision = Decision.APPROVED if approve else Decision.REJECTED
    step.decided_at = now
    step.comment = comment[:1000]
    step.save(update_fields=["decision", "decided_at", "comment", "updated_at"])

    label = REQUEST_TYPES.get(instance.entity_type, instance.entity_type)
    if not approve:
        instance.status = Status.REJECTED
        instance.decided_at = now
        instance.save(update_fields=["status", "decided_at", "updated_at"])
        _notify(
            instance.requested_by,
            title="So'rovingiz rad etildi",
            message=f"{instance.title or label}" + (f" — {comment}" if comment else ""),
            kind=Notification.Type.ERROR,
        )
        return instance

    nxt = current_step(instance)
    if nxt is None:
        instance.status = Status.APPROVED
        instance.decided_at = now
        instance.save(update_fields=["status", "decided_at", "updated_at"])
        _notify(
            instance.requested_by,
            title="So'rovingiz tasdiqlandi",
            message=instance.title or label,
            kind=Notification.Type.SUCCESS,
        )
    else:
        _notify(
            nxt.approver,
            title="Tasdiqlash navbati sizda",
            message=f"{instance.requested_by.full_name}: {instance.title or label}",
            kind=Notification.Type.WARNING,
        )
    return instance


@transaction.atomic
def cancel_request(*, actor: User, instance: ApprovalInstance) -> ApprovalInstance:
    instance = ApprovalInstance.objects.select_for_update().get(pk=instance.pk)
    if instance.status != Status.PENDING:
        raise ValidationError("Faqat kutilayotgan so'rovni bekor qilish mumkin")
    if instance.requested_by_id != actor.id and not actor.has_capability("workflow.manage"):
        raise PermissionDenied("Faqat so'rovchi yoki rahbar bekor qila oladi")
    instance.status = Status.CANCELLED
    instance.decided_at = timezone.now()
    instance.save(update_fields=["status", "decided_at", "updated_at"])
    return instance
