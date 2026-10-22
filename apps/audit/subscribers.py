from core.context import get_context
from core.events import Event, subscribe

from .models import AuditLog


@subscribe("*")
def write_audit_log(event: Event) -> None:
    if not event.audit:
        return
    ctx = get_context()
    AuditLog.objects.create(
        actor_id=event.actor_id,
        branch_id=event.branch_id,
        event_name=event.name,
        aggregate_type=event.aggregate_type,
        aggregate_id=event.aggregate_id,
        payload=event.json_payload(),
        ip=ctx.ip or "",
        user_agent=ctx.user_agent,
        request_id=ctx.request_id,
        created_at=event.occurred_at,
    )
