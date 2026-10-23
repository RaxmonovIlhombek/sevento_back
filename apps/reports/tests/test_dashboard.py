"""Rahbar dashboardi: KPI, davr solishtiruvi, grafik qatorlari, huquqlar."""

from datetime import date

import pytest

from apps.reports.dashboard import period_bounds

pytestmark = pytest.mark.django_db

URL = "/api/v1/reports/dashboard/"


def test_today(owner_client, world):
    data = owner_client.get(URL).json()
    assert data["period"]["key"] == "today" and data["base_currency"] == "USD"
    kpi = data["kpi"]
    # savdo 6,40 − qaytarish 0,80 = 5,60; 2 ta savdo, o'rtacha chek 3,20; foyda 2,80
    assert kpi["revenue"] == {"value": "5.60", "previous": "0.00", "change": None}
    assert kpi["sales_count"]["value"] == "2.00" and kpi["average_check"]["value"] == "3.20"
    assert kpi["returns"]["value"] == "0.80" and kpi["profit"]["value"] == "2.80"
    assert sum(float(p["revenue"]) for p in data["series"]) == pytest.approx(5.60)
    assert data["series"][0]["label"] == "00:00"
    assert data["top_products"][0]["name"] == "Cola 1L"
    assert data["payment_methods"] == [{"method": "Naqd pul", "amount": "4.00"}]
    assert data["cash"][0]["currency"] == "UZS" and data["cash"][0]["balance"] == "40000.0000"
    assert data["debts"] == {"open": "2.40", "overdue": "0.00", "overdue_count": 0}
    assert data["inventory"]["stock_value"] == "4.40"
    assert data["by_branch"][0]["branch"] == "Toshkent 1"


def test_week_series_has_every_day(owner_client, world):
    data = owner_client.get(URL, {"period": "7d"}).json()
    assert len(data["series"]) == 7
    assert data["series"][-1]["revenue"] == "5.60" and data["series"][0]["revenue"] == "0.00"


def test_period_bounds():
    assert period_bounds("7d", date(2026, 10, 23)) == (
        date(2026, 10, 17),
        date(2026, 10, 23),
        date(2026, 10, 10),
        date(2026, 10, 16),
    )
    start, end, prev_start, prev_end = period_bounds("month", date(2026, 3, 31))
    assert (start, end, prev_start, prev_end) == (
        date(2026, 3, 1),
        date(2026, 3, 31),
        date(2026, 2, 1),
        date(2026, 2, 28),
    )


def test_permissions(seller_client, roles, accountant, as_user, storekeeper, branch2, world):
    assert seller_client.get(URL).status_code == 403
    assert as_user(storekeeper).get(URL).status_code == 403
    roles["accountant"].capabilities = [
        c for c in roles["accountant"].capabilities if c != "reports.financial"
    ]
    roles["accountant"].save()
    from apps.accounts.models import User

    data = as_user(User.objects.get(pk=accountant.pk)).get(URL).json()
    assert "profit" not in data["kpi"] and data["show_profit"] is False
    assert "profit" not in data["series"][0]


def test_branch_scope(owner_client, world, branch, branch2):
    other = owner_client.get(URL, {"branch": branch2.id}).json()
    assert other["kpi"]["revenue"]["value"] == "0.00"
    bad = owner_client.get(URL, {"period": "year"})
    assert bad.status_code == 400
