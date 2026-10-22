from django.db import transaction

from . import events
from .models import Branch

TRACKED_FIELDS = ("code", "name", "type", "address", "phone", "is_active", "settings")


def create_branch(*, actor, **fields) -> Branch:
    with transaction.atomic():
        branch = Branch.objects.create(**fields)
        events.BranchCreated.publish_from(
            actor=actor,
            branch_id=branch.pk,
            code=branch.code,
            branch_name=branch.name,
            type=branch.type,
        )
    return branch


def update_branch(*, actor, branch: Branch, **fields) -> Branch:
    with transaction.atomic():
        changes = {}
        for name, value in fields.items():
            old = getattr(branch, name)
            if old != value:
                changes[name] = {"old": old, "new": value}
                setattr(branch, name, value)
        branch.save()
        if changes:
            events.BranchUpdated.publish_from(
                actor=actor, branch_id=branch.pk, code=branch.code, changes=changes
            )
    return branch
