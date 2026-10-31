from django.db import transaction
from django.utils import timezone

from core.models import DocumentSequence
from .models import JournalEntry, JournalLine


def _next_number(branch_id, year):
    seq, _ = DocumentSequence.objects.select_for_update().get_or_create(
        doc_type="JE", branch_id=branch_id or 0, year=year
    )
    seq.last_number += 1
    seq.save(update_fields=["last_number"])
    return f"JE-{year}-{seq.last_number:05d}"


@transaction.atomic
def create_entry(
    *,
    user,
    date,
    fiscal_period,
    branch=None,
    description="",
    lines,
):
    if not lines:
        raise ValueError("Kamida bitta qator kerak")
    branch_id = getattr(branch, "pk", branch)
    entry = JournalEntry.objects.create(
        number=_next_number(branch_id, date.year),
        date=date,
        fiscal_period=fiscal_period,
        branch=branch,
        description=description,
        status=JournalEntry.Status.DRAFT,
        created_by=user,
    )
    for ln in lines:
        JournalLine.objects.create(
            entry=entry,
            account=ln["account"],
            description=ln.get("description", ""),
            debit=ln.get("debit", 0),
            credit=ln.get("credit", 0),
        )
    return entry


@transaction.atomic
def post_entry(*, entry, user):
    if entry.status != JournalEntry.Status.DRAFT:
        raise ValueError("Faqat qoralama yozuvni o'tkazish mumkin")
    if entry.fiscal_period.is_closed:
        raise ValueError("Moliyaviy davr yopilgan")
    total_debit = sum((l.debit for l in entry.lines.all()), 0)
    total_credit = sum((l.credit for l in entry.lines.all()), 0)
    if total_debit != total_credit:
        raise ValueError(f"Debet ({total_debit}) va kredit ({total_credit}) teng emas")
    if total_debit == 0:
        raise ValueError("Nol summalik yozuvni o'tkazib bo'lmaydi")
    for ln in entry.lines.all():
        if ln.debit < 0 or ln.credit < 0:
            raise ValueError("Manfiy summa mumkin emas")
        if ln.debit > 0 and ln.credit > 0:
            raise ValueError("Bir qatorda debet va kredit birga bo'lishi mumkin emas")
        if not ln.account.is_postable:
            raise ValueError(f"{ln.account.code} hisobga yozuv mumkin emas (barg emas)")
    entry.status = JournalEntry.Status.POSTED
    entry.posted_at = timezone.now()
    entry.posted_by = user
    entry.save(update_fields=["status", "posted_at", "posted_by", "updated_at"])
    return entry


@transaction.atomic
def reverse_entry(*, entry, user, date=None, description=None):
    if entry.status != JournalEntry.Status.POSTED:
        raise ValueError("Faqat o'tkazilgan yozuvni bekor qilish mumkin")
    if entry.reversals.exists():
        raise ValueError("Bu yozuv allaqachon bekor qilingan")
    new_date = date or entry.date
    new_entry = create_entry(
        user=user,
        date=new_date,
        fiscal_period=entry.fiscal_period,
        branch=entry.branch,
        description=description or f"Bekor qilindi: {entry.number}",
        lines=[
            {
                "account": ln.account,
                "description": ln.description,
                "debit": ln.credit,
                "credit": ln.debit,
            }
            for ln in entry.lines.all()
        ],
    )
    post_entry(entry=new_entry, user=user)
    entry.status = JournalEntry.Status.REVERSED
    entry.reversed_by_entry = new_entry
    entry.save(update_fields=["status", "reversed_by_entry", "updated_at"])
    return new_entry
