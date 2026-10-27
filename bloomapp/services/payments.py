"""Razorpay integration: creating payment orders and checking signatures."""
import hashlib
import hmac

import razorpay
from django.conf import settings


def get_client():
    return razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_SECRET_KEY))


def amount_in_paise(amount):
    return int(round(float(amount) * 100))


def create_razorpay_order(order):
    """Create the Razorpay order a customer pays against, for the exact order total."""
    rzp_order = get_client().order.create({
        'amount': amount_in_paise(order.total_amount),
        'currency': 'INR',
        'receipt': f'bloomify_order_{order.id}',
        'payment_capture': '1',
    })
    return rzp_order['id']


def verify_payment_signature(razorpay_order_id, razorpay_payment_id, signature):
    """True if Razorpay really reported this payment for this Razorpay order."""
    try:
        get_client().utility.verify_payment_signature({
            'razorpay_order_id': razorpay_order_id,
            'razorpay_payment_id': razorpay_payment_id,
            'razorpay_signature': signature,
        })
        return True
    except razorpay.errors.SignatureVerificationError:
        return False


def verify_webhook_signature(raw_body, signature):
    """True if a webhook call was signed with our Razorpay webhook secret."""
    secret = settings.RAZORPAY_WEBHOOK_SECRET
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
