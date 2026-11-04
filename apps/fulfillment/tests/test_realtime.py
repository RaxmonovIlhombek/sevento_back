"""Yetkazish holati o'zgarganda nuqta guruhiga WebSocket xabari ketadi (minimal payload)."""

import pytest

from apps.fulfillment.events import FulfillmentStatusChanged
from apps.realtime.router import resolve

pytestmark = pytest.mark.django_db


def test_status_changed_goes_to_branch_group(branch):
    event = FulfillmentStatusChanged(
        branch_id=branch.id,
        fulfillment_id=7,
        sale_id=3,
        number="S-TSH1-26-000003",
        status="packed",
        previous_status="pending",
        courier_id=None,
        note="ichki izoh",
    )
    [out] = resolve(event)
    assert out.group == f"branch_{branch.id}"
    assert out.message["type"] == "fulfillment.status_changed"
    assert out.message["payload"] == {
        "branch_id": branch.id,
        "fulfillment_id": 7,
        "number": "S-TSH1-26-000003",
        "status": "packed",
        "previous_status": "pending",
    }
    assert "note" not in out.message["payload"]
