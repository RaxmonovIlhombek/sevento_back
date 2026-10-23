from core.exceptions import BusinessRuleError


class InsufficientStock(BusinessRuleError):
    code = "insufficient_stock"
    message = "Omborda yetarli tovar yo'q"


class BatchConsumed(BusinessRuleError):
    code = "batch_consumed"
    message = "Bu kirim partiyasidan tovar allaqachon chiqim qilingan"
