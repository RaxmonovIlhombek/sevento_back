from dataclasses import dataclass, field
from typing import Any

from core.events import Event


@dataclass(frozen=True, kw_only=True)
class BranchCreated(Event):
    name = "branch.created"
    aggregate_type = "branch"
    aggregate_id_field = "branch_id"

    code: str
    branch_name: str
    type: str


@dataclass(frozen=True, kw_only=True)
class BranchUpdated(Event):
    name = "branch.updated"
    aggregate_type = "branch"
    aggregate_id_field = "branch_id"

    code: str
    changes: dict[str, Any] = field(default_factory=dict)
