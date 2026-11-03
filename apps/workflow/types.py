"""So'rov turlari. Qoida (ApprovalRule.entity_type) va so'rov shu kodlardan birini ishlatadi."""

REQUEST_TYPES: dict[str, str] = {
    "discount": "Chegirma",
    "writeoff": "Hisobdan chiqarish",
    "expense": "Xarajat",
    "refund": "Pul qaytarish",
    "purchase": "Xarid",
    "other": "Boshqa",
}
