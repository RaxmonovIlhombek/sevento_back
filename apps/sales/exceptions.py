from core.exceptions import BusinessRuleError


class TotalMismatch(BusinessRuleError):
    code = "total_mismatch"
    message = "Narxlar o'zgargan — savatni yangilang"


class PaymentInsufficient(BusinessRuleError):
    status_code = 400
    code = "payment_insufficient"
    message = "To'lov summasi yetarli emas"


class DiscountForbidden(BusinessRuleError):
    status_code = 403
    code = "discount_forbidden"
    message = "Chegirma berish huquqi yo'q"


class SaleHasReturns(BusinessRuleError):
    code = "sale_has_returns"
    message = "Savdo bo'yicha qaytarish bor — bekor qilib bo'lmaydi (qolganini qaytarish orqali)"
