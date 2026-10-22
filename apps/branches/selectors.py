from django.db.models import QuerySet

from core.access import scope_queryset_to_user

from .models import Branch


def all_branches() -> QuerySet[Branch]:
    return Branch.objects.all()


def active_branches() -> QuerySet[Branch]:
    return Branch.objects.filter(is_active=True)


def get_branch(branch_id: int) -> Branch | None:
    return Branch.objects.filter(pk=branch_id).first()


def branches_for_user(user) -> QuerySet[Branch]:
    return scope_queryset_to_user(Branch.objects.all(), user, branch_field="pk")
