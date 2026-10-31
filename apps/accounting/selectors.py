from django.db.models import Sum

from .models import Account, JournalEntry, JournalLine


def trial_balance(*, fiscal_period=None, branch=None, date_to=None):
    qs = JournalLine.objects.filter(entry__status=JournalEntry.Status.POSTED)
    if fiscal_period is not None:
        qs = qs.filter(entry__fiscal_period=fiscal_period)
    if branch is not None:
        qs = qs.filter(entry__branch=branch)
    if date_to is not None:
        qs = qs.filter(entry__date__lte=date_to)
    agg = (
        qs.values("account_id")
        .annotate(debit=Sum("debit"), credit=Sum("credit"))
    )
    by_account = {row["account_id"]: row for row in agg}
    accounts = Account.objects.filter(is_active=True).order_by("code")
    rows = []
    for acc in accounts:
        row = by_account.get(acc.pk, {"debit": 0, "credit": 0})
        d = row["debit"] or 0
        c = row["credit"] or 0
        if acc.is_debit_normal:
            balance = d - c
        else:
            balance = c - d
        rows.append(
            {
                "account": acc,
                "debit": d,
                "credit": c,
                "balance": balance,
            }
        )
    return rows
