from .base import ProviderResult


class ManualProvider:
    """Naqd pul, karta terminali, bank o'tkazmasi — kassir tasdiqlaydi, tashqi API yo'q."""

    key = "manual"
    name = "Qo'lda (naqd, terminal, o'tkazma)"

    def charge(self, *, amount, currency_code: str, reference: str) -> ProviderResult:
        return ProviderResult(ok=True)

    def refund(self, *, amount, currency_code: str, original_reference: str) -> ProviderResult:
        return ProviderResult(ok=True)
