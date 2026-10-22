import json
import types
import typing
from dataclasses import asdict, dataclass, field, fields
from datetime import date, datetime
from decimal import Decimal
from typing import Any, ClassVar

from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone

META_FIELDS = frozenset({"occurred_at", "actor_id", "branch_id"})
_EVENT_CLASSES: dict[str, type["Event"]] = {}


@dataclass(frozen=True, kw_only=True)
class Event:
    """Barcha hodisalarning bazasi. Avlod `name` va `aggregate_type` ni belgilaydi.

    `aggregate_id_field` — payload dagi qaysi maydon aggregat id si (masalan "sale_id").
    `audit=False` — audit jurnaliga yozilmaydi (masalan stock.changed: harakat jurnali o'zi tarix).
    """

    name: ClassVar[str] = ""
    aggregate_type: ClassVar[str] = ""
    aggregate_id_field: ClassVar[str | None] = None
    audit: ClassVar[bool] = True

    occurred_at: datetime = field(default_factory=timezone.now)
    actor_id: int | None = None
    branch_id: int | None = None

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls.name:
            existing = _EVENT_CLASSES.get(cls.name)
            if existing is not None and existing is not cls:
                raise TypeError(f"Hodisa nomi takrorlangan: {cls.name}")
            _EVENT_CLASSES[cls.name] = cls

    @property
    def aggregate_id(self) -> int | None:
        if self.aggregate_id_field is None:
            return None
        return getattr(self, self.aggregate_id_field, None)

    def payload(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if k not in META_FIELDS}

    def json_payload(self) -> dict[str, Any]:
        """JSON ga yaroqli nusxa (Decimal → satr, datetime → ISO)."""
        return json.loads(json.dumps(self.payload(), cls=DjangoJSONEncoder))

    @classmethod
    def from_outbox(cls, row) -> "Event":
        event_cls = get_event_class(row.name)
        kwargs = _coerce_payload(event_cls, row.payload)
        return event_cls(
            occurred_at=row.occurred_at,
            actor_id=row.actor_id,
            branch_id=row.branch_id,
            **kwargs,
        )

    @classmethod
    def publish_from(cls, *, actor=None, **kwargs) -> "Event":
        """Qulaylik: hodisani yaratib darhol publish qiladi. actor — User yoki None."""
        from .dispatcher import publish

        actor_id = getattr(actor, "pk", None) if actor is not None else None
        event = cls(actor_id=actor_id, **kwargs)
        publish(event)
        return event


def get_event_class(name: str) -> type[Event]:
    try:
        return _EVENT_CLASSES[name]
    except KeyError:
        raise KeyError(f"Noma'lum hodisa: {name}") from None


def all_event_names() -> list[str]:
    return sorted(_EVENT_CLASSES)


def _coerce_payload(event_cls: type[Event], payload: dict) -> dict:
    """Outbox dan o'qilgan JSON ni maydon turlariga qaytaradi (Decimal, datetime, date)."""
    hints = typing.get_type_hints(event_cls)
    result = {}
    for f in fields(event_cls):
        if f.name in META_FIELDS or f.name not in payload:
            continue
        result[f.name] = _coerce_value(hints.get(f.name), payload[f.name])
    return result


def _coerce_value(hint, value):
    if value is None or hint is None:
        return value
    origin = typing.get_origin(hint)
    if origin is types.UnionType or origin is typing.Union:
        for arg in typing.get_args(hint):
            if arg is type(None):
                continue
            try:
                return _coerce_value(arg, value)
            except (ValueError, TypeError):
                continue
        return value
    if hint is Decimal:
        return Decimal(str(value))
    if hint is datetime:
        return datetime.fromisoformat(value) if isinstance(value, str) else value
    if hint is date:
        return date.fromisoformat(value) if isinstance(value, str) else value
    return value
