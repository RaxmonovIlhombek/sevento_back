from core.exceptions import BusinessRuleError


class InsufficientCash(BusinessRuleError):
    code = "insufficient_cash"
    message = "Kassada yetarli naqd pul yo'q"


class ProviderUnavailable(BusinessRuleError):
    code = "provider_unavailable"
    message = "To'lov provayderi ulanmagan"


class PaymentDeclined(BusinessRuleError):
    code = "payment_declined"
    message = "To'lov rad etildi"


class NoCashMethod(BusinessRuleError):
    code = "no_cash_method"
    message = "Faol naqd to'lov turi yo'q (qaytim berish uchun kerak)"
