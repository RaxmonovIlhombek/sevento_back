from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ProviderResult:
    ok: bool
    reference: str = ""
    message: str = ""


class PaymentProvider(Protocol):
    """To'lov provayderi (adapter). Naqd/terminal — darhol; Click/Payme — keyin shu interfeys bilan.

    charge/refund service tranzaksiyasi ichida chaqiriladi; tashqi API chaqiradigan provayderlar
    (Click, Payme) callback/holat tekshiruvi bilan alohida oqimda ishlaydi (9+ bosqich).
    """

    key: str
    name: str

    def charge(self, *, amount, currency_code: str, reference: str) -> ProviderResult: ...

    def refund(self, *, amount, currency_code: str, original_reference: str) -> ProviderResult: ...
