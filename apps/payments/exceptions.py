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


class ShiftClosed(BusinessRuleError):
    code = "shift_closed"
    message = "Kassa smenasi ochilmagan"


class ShiftAlreadyOpen(BusinessRuleError):
    code = "shift_already_open"
    message = "Bu nuqtada smena allaqachon ochiq"


class CreditLimitExceeded(BusinessRuleError):
    code = "credit_limit_exceeded"
    message = "Mijozning kredit limiti yetarli emas"


class DebtHasPayments(BusinessRuleError):
    code = "debt_has_payments"
    message = "Qarz bo'yicha to'lov qilingan — avval to'lovni qaytaring"


class PaymentExceedsDebt(BusinessRuleError):
    status_code = 400
    code = "payment_exceeds_debt"
    message = "To'lov summasi qarzdan katta"


class NoOpenDebts(BusinessRuleError):
    code = "no_open_debts"
    message = "Mijozning ochiq qarzi yo'q"


class CategoryNotManual(BusinessRuleError):
    status_code = 400
    code = "category_not_manual"
    message = "Bu turdagi kassa yozuvini qo'lda kiritib bo'lmaydi"


class RefundNotAllowed(BusinessRuleError):
    code = "refund_not_allowed"
    message = "Bu to'lovni bu yerda qaytarib bo'lmaydi"
