from dataclasses import dataclass
from typing import Any

from .base import Event


@dataclass(frozen=True, kw_only=True)
class SettingChanged(Event):
    name = "setting.changed"
    aggregate_type = "system_setting"
    aggregate_id_field = "setting_id"

    setting_id: int
    key: str
    old_value: Any
    new_value: Any
