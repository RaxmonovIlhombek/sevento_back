"""To'lov qoidalari: turini tahrirlash, summa, faol emas tur, provayder rad etishi, naqd tur."""

from decimal import Decimal as D

import pytest

from apps.currency.models import Currency
from apps.payments import services
from apps.payments.exceptions import NoCashMethod, PaymentDeclined
from apps.payments.models import Payment, PaymentMethod
from apps.payments.providers.base import ProviderResult
from apps.payments.services import payments as payment_module
from apps.payments.types import PaymentDoc
from core.exceptions import BusinessRuleError
from core.models import OutboxEvent

pytestmark = pytest.mark.django_db

DOC = PaymentDoc(type="sale", id=1, number="S-TEST-1")


@pytest.fixture
def uzs(db):
    return Currency.objects.get(code="UZS")


class Declining:
    def charge(self, **kwargs):
        return ProviderResult(ok=False, message="Karta bloklangan")

    def refund(self, **kwargs):
        return ProviderResult(ok=False)


def test_edit_payment_method_event_only_on_change(owner, django_capture_on_commit_callbacks):
    card = PaymentMethod.objects.get(code="card")
    with django_capture_on_commit_callbacks(execute=True):
        services.save_payment_method(actor=owner, method=card, name="Humo / Uzcard")
        services.save_payment_method(actor=owner, method=card, name="Humo / Uzcard")
    events = OutboxEvent.objects.filter(name="payment_method.saved")
    assert events.count() == 1
    assert events.get().payload["changes"]["name"]["new"] == "Humo / Uzcard"


def test_unknown_provider_rejected(owner):
    with pytest.raises(BusinessRuleError):
        services.save_payment_method(
            actor=owner, method=PaymentMethod.objects.get(code="card"), provider="yoq"
        )


def test_amount_must_be_positive(owner, branch, uzs):
    cash = PaymentMethod.objects.get(code="cash")
    with pytest.raises(BusinessRuleError) as exc:
        services.receive_payment(
            actor=owner, branch=branch, method=cash, currency=uzs, amount=D("0"), doc=DOC
        )
    assert exc.value.code == "invalid_amount"


def test_inactive_method_rejected(owner, branch, uzs):
    card = PaymentMethod.objects.get(code="card")
    card.is_active = False
    card.save()
    with pytest.raises(BusinessRuleError) as exc:
        services.receive_payment(
            actor=owner, branch=branch, method=card, currency=uzs, amount=D("1000"), doc=DOC
        )
    assert exc.value.code == "method_inactive"
    with pytest.raises(BusinessRuleError) as exc:
        services.refund_to_customer(
            actor=owner, branch=branch, currency=uzs, amount=D("1000"), doc=DOC, method=card
        )
    assert exc.value.code == "method_inactive"


def test_provider_decline_creates_no_payment(owner, branch, uzs, monkeypatch):
    monkeypatch.setattr(payment_module, "get_provider", lambda key: Declining())
    card = PaymentMethod.objects.get(code="card")
    with pytest.raises(PaymentDeclined) as exc:
        services.receive_payment(
            actor=owner, branch=branch, method=card, currency=uzs, amount=D("5000"), doc=DOC
        )
    assert exc.value.message == "Karta bloklangan"
    with pytest.raises(PaymentDeclined):
        services.refund_to_customer(
            actor=owner, branch=branch, currency=uzs, amount=D("5000"), doc=DOC, method=card
        )
    assert not Payment.objects.exists()


def test_change_and_refund_need_active_cash_method(owner, branch, uzs):
    PaymentMethod.objects.filter(is_cash=True).update(is_active=False)
    with pytest.raises(NoCashMethod):
        services.give_change(actor=owner, branch=branch, currency=uzs, amount=D("100"), doc=DOC)
    with pytest.raises(NoCashMethod):
        services.refund_to_customer(
            actor=owner, branch=branch, currency=uzs, amount=D("100"), doc=DOC
        )
