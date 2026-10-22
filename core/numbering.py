"""Hujjat raqamlari: S-TSH1-26-000123 (tur-nuqta kodi-yil-tartib)."""

from django.db import transaction
from django.utils import timezone

from .models import DocumentSequence


def next_number(*, doc_type: str, branch_id: int, branch_code: str, year: int | None = None) -> str:
    year = year or timezone.localdate().year
    with transaction.atomic():
        seq, _ = DocumentSequence.objects.select_for_update().get_or_create(
            doc_type=doc_type, branch_id=branch_id, year=year
        )
        seq.last_number += 1
        seq.save(update_fields=["last_number"])
    return f"{doc_type}-{branch_code}-{year % 100:02d}-{seq.last_number:06d}"
