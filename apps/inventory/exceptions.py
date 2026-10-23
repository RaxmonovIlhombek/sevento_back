from core.exceptions import BusinessRuleError


class InsufficientStock(BusinessRuleError):
    code = "insufficient_stock"
    message = "Omborda yetarli tovar yo'q"


class BatchConsumed(BusinessRuleError):
    code = "batch_consumed"
    message = "Bu kirim partiyasidan tovar allaqachon chiqim qilingan"


class CountInProgress(BusinessRuleError):
    code = "count_in_progress"
    message = "Bu nuqtada yakunlanmagan inventarizatsiya bor"


class CountEmpty(BusinessRuleError):
    code = "count_empty"
    message = "Birorta ham tovar sanalmagan"


class SystemWriteOff(BusinessRuleError):
    code = "write_off_system"
    message = "Ko'chirish kamomadi hujjatini alohida bekor qilib bo'lmaydi"
