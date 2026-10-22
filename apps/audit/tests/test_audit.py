from dataclasses import dataclass

import pytest
from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditLog
from core.events import Event, publish

pytestmark = pytest.mark.django_db

URL = "/api/v1/audit/"


@dataclass(frozen=True, kw_only=True)
class QuietEvent(Event):
    name = "test.quiet"
    aggregate_type = "thing"
    audit = False
    thing_id: int


@dataclass(frozen=True, kw_only=True)
class LoudEvent(Event):
    name = "test.loud"
    aggregate_type = "thing"
    aggregate_id_field = "thing_id"
    thing_id: int


def test_audit_false_event_is_skipped(django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        with transaction.atomic():
            publish(QuietEvent(thing_id=1))
            publish(LoudEvent(thing_id=2, branch_id=None))
    assert list(AuditLog.objects.values_list("event_name", flat=True)) == ["test.loud"]
    log = AuditLog.objects.get()
    assert log.aggregate_id == 2
    assert log.payload == {"thing_id": 2}


def test_list_requires_capability(seller_client, accountant, as_user, owner_client):
    assert seller_client.get(URL).status_code == 403
    assert as_user(accountant).get(URL).status_code == 403
    assert owner_client.get(URL).status_code == 200


def test_list_filters(owner_client, owner, branch, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        owner_client.post("/api/v1/branches/", {"code": "A1", "name": "A"})
        owner_client.patch(f"/api/v1/branches/{branch.id}/", {"name": "B"})

    body = owner_client.get(URL).json()
    assert body["count"] == 2
    assert body["results"][0]["event_name"] == "branch.updated"  # eng yangi birinchi
    assert body["results"][0]["actor_username"] == "rahbar"
    assert body["results"][0]["branch_name"] == "B"

    assert owner_client.get(URL, {"event_name": "branch.created"}).json()["count"] == 1
    assert owner_client.get(URL, {"event_prefix": "branch."}).json()["count"] == 2
    assert owner_client.get(URL, {"branch": branch.id}).json()["count"] == 1
    assert owner_client.get(URL, {"actor": owner.id}).json()["count"] == 2
    today = timezone.localdate().isoformat()
    assert owner_client.get(URL, {"date_from": today, "date_to": today}).json()["count"] == 2
    assert owner_client.get(URL, {"date_to": "2000-01-01"}).json()["count"] == 0
    assert (
        owner_client.get(URL, {"aggregate_type": "branch", "aggregate_id": branch.id}).json()[
            "count"
        ]
        == 1
    )


def test_audit_is_read_only(owner_client):
    assert owner_client.post(URL, {}).status_code == 405
