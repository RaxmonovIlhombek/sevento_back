"""Biznes qoidasi xatolari. Service lar shularni ko'taradi, API qatlami yagona formatga o'giradi."""


class BusinessRuleError(Exception):
    status_code = 409
    code = "business_rule_violation"
    message = "Amalni bajarib bo'lmaydi"

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        details: list[dict] | None = None,
        status_code: int | None = None,
    ):
        self.message = message or self.message
        self.code = code or self.code
        self.details = details or []
        if status_code is not None:
            self.status_code = status_code
        super().__init__(self.message)


class NotFoundError(BusinessRuleError):
    status_code = 404
    code = "not_found"
    message = "Topilmadi"


class BranchForbidden(BusinessRuleError):
    status_code = 403
    code = "branch_forbidden"
    message = "Bu nuqta ma'lumotlariga ruxsat yo'q"


class InvalidStatusTransition(BusinessRuleError):
    code = "invalid_status_transition"
    message = "Bu holatdan o'tish mumkin emas"


class DuplicateRequest(BusinessRuleError):
    code = "duplicate_request"
    message = "Bu so'rov allaqachon bajarilmoqda"


class EventOutsideTransaction(RuntimeError):
    """publish() transaction.atomic tashqarisida chaqirildi — dasturchi xatosi."""
