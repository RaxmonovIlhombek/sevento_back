"""Biznes sozlamalari ta'riflari. Qiymat MB da (SystemSetting), bu yerda faqat kalit, tur, default.

Har app o'z sozlamalarini settings_defs.py faylida register() bilan qo'shadi
(core.apps.CoreConfig.ready() avtomatik yuklaydi).
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

SettingType = Literal["str", "int", "decimal", "bool", "json", "choice"]


@dataclass(frozen=True)
class SettingDef:
    key: str
    type: SettingType
    default: Any
    description: str
    choices: tuple[str, ...] = ()

    def coerce(self, value: Any) -> Any:
        """JSON dan kelgan qiymatni turga keltiradi; noto'g'ri bo'lsa ValueError."""
        match self.type:
            case "str":
                if not isinstance(value, str):
                    raise ValueError("satr bo'lishi kerak")
                return value
            case "choice":
                if value not in self.choices:
                    raise ValueError(f"ruxsat etilgan qiymatlar: {', '.join(self.choices)}")
                return value
            case "int":
                if isinstance(value, bool) or not isinstance(value, int):
                    raise ValueError("butun son bo'lishi kerak")
                return value
            case "bool":
                if not isinstance(value, bool):
                    raise ValueError("true yoki false bo'lishi kerak")
                return value
            case "decimal":
                try:
                    return Decimal(str(value))
                except (InvalidOperation, TypeError) as exc:
                    raise ValueError("son bo'lishi kerak") from exc
            case "json":
                return value
        raise ValueError("noma'lum tur")

    def to_json(self, value: Any) -> Any:
        if self.type == "decimal":
            return str(value)
        return value


_REGISTRY: dict[str, SettingDef] = {}


def register(*defs: SettingDef) -> None:
    for d in defs:
        _REGISTRY[d.key] = d


def get_def(key: str) -> SettingDef:
    try:
        return _REGISTRY[key]
    except KeyError:
        raise KeyError(f"Noma'lum sozlama: {key}") from None


def all_defs() -> list[SettingDef]:
    return [_REGISTRY[k] for k in sorted(_REGISTRY)]


register(
    SettingDef(
        key="currency.base_code",
        type="str",
        default="USD",
        description="Tannarx, foyda va kredit limiti hisoblanadigan asosiy valyuta kodi",
    ),
    SettingDef(
        key="currency.rate_provider",
        type="choice",
        default="cbu",
        choices=("cbu", "manual"),
        description="Valyuta kursi manbai",
    ),
    SettingDef(
        key="inventory.costing_method",
        type="choice",
        default="fifo",
        choices=("fifo",),
        description="Tannarx hisoblash usuli",
    ),
    SettingDef(
        key="inventory.default_min_quantity",
        type="decimal",
        default="5",
        description="Tovar uchun alohida berilmagan bo'lsa minimal qoldiq",
    ),
    SettingDef(
        key="sales.max_seller_discount_percent",
        type="decimal",
        default="10",
        description="Sotuvchi bera oladigan maksimal chegirma (%)",
    ),
    SettingDef(
        key="payments.default_credit_limit_base",
        type="decimal",
        default="0",
        description="Yangi mijoz uchun kredit limiti (asosiy valyutada)",
    ),
    SettingDef(
        key="payments.credit_limit_warning_percent",
        type="decimal",
        default="80",
        description="Limitga yaqinlashganda ogohlantirish chegarasi (%)",
    ),
    SettingDef(
        key="payments.default_due_days",
        type="int",
        default=30,
        description="Nasiya muddati (kun)",
    ),
)
