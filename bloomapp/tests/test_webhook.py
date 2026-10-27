import hashlib
import hmac
import json

import pytest
from django.core import mail
from django.urls import reverse

from bloomapp.models import CartItem, Order, Payment
from bloomapp.services import orders as order_service
from bloomapp.services.orders import CheckoutDetails

from .conftest import CHECKOUT

pytestmark = pytest.mark.django_db
WEBHOOK_SECRET = 'test-webhook-secret'


@pytest.fixture
def online_order(customer, product):
    item = CartItem.objects.create(user=customer, product=product, quantity=1)
    return order_service.place_order(customer, [item], CheckoutDetails(**{**CHECKOUT, 'payment_mode': 'online'}))


def event(order, event_type='payment.captured', amount=None, payment_id='pay_hook1'):
    return {
        'event': event_type,
        'payload': {
            'payment': {
                'entity': {
                    'id': payment_id,
                    'order_id': order.razorpay_order_id,
                    'amount': amount if amount is not None else int(order.total_amount * 100),
                }
            }
        },
    }


def post_webhook(client, payload, secret=WEBHOOK_SECRET):
    body = json.dumps(payload).encode()
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return client.post(
        reverse('razorpay_webhook'), body, content_type='application/json', HTTP_X_RAZORPAY_SIGNATURE=signature
    )


def payment_status(order):
    return Payment.objects.get(order=order).status


def test_captured_payment_confirms_order(client, online_order):
    assert post_webhook(client, event(online_order)).status_code == 200
    payment = Payment.objects.get(order=online_order)
    assert (payment.status, payment.transaction_id) == ('completed', 'pay_hook1')
    assert len(mail.outbox) == 1


def test_bad_signature_is_rejected(client, online_order):
    response = post_webhook(client, event(online_order), secret='wrong-secret')
    assert response.status_code == 400
    assert payment_status(online_order) == 'pending'


def test_missing_signature_is_rejected(client, online_order):
    response = client.post(
        reverse('razorpay_webhook'), json.dumps(event(online_order)), content_type='application/json'
    )
    assert response.status_code == 400


def test_wrong_amount_does_not_confirm(client, online_order):
    post_webhook(client, event(online_order, amount=100))
    assert payment_status(online_order) == 'pending'


def test_failed_payment_leaves_order_waiting(client, online_order):
    post_webhook(client, event(online_order, event_type='payment.failed'))
    assert payment_status(online_order) == 'pending'


def test_unknown_order_is_acknowledged(client, online_order):
    payload = event(online_order)
    payload['payload']['payment']['entity']['order_id'] = 'order_SOMEONE_ELSE'
    assert post_webhook(client, payload).status_code == 200
    assert payment_status(online_order) == 'pending'


def test_webhook_and_browser_confirmation_only_count_once(client, online_order):
    post_webhook(client, event(online_order))
    post_webhook(client, event(online_order))
    assert order_service.mark_order_paid(online_order, 'pay_hook1') == 'already_paid'
    assert len(mail.outbox) == 1


def test_payment_for_expired_order_is_flagged_for_refund(client, online_order):
    order_service.release_order(online_order, payment_status='expired')
    post_webhook(client, event(online_order))
    assert payment_status(online_order) == 'refund_due'
    assert Order.objects.get(pk=online_order.pk).status == 'cancelled'
