"""Online payment: the Razorpay payment page, browser confirmation and webhook."""
import json
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from bloomapp.models import Order, Payment
from bloomapp.services import orders as order_service
from bloomapp.services import payments

logger = logging.getLogger(__name__)


def payment_page_context(order):
    return {
        'order': order,
        'razorpay_order_id': order.razorpay_order_id,
        'amount': payments.amount_in_paise(order.total_amount),
        'key': settings.RAZORPAY_KEY_ID,
        'currency': 'INR',
    }


@login_required
def payment_view(request):
    """Return to the payment page for an order that is still waiting to be paid."""
    order_service.release_expired_online_orders()
    order_id = request.session.get('pending_order_id')
    if not order_id:
        return redirect('checkout')
    order = get_object_or_404(Order, id=order_id, user=request.user)
    payment = Payment.objects.filter(order=order).first()
    if order.status == 'cancelled':
        request.session.pop('pending_order_id', None)
        messages.error(request, 'This order expired before payment was completed. Please order again.')
        return redirect('cart')
    if payment and payment.status == 'completed':
        return redirect('order_success', pk=order.id)
    return render(request, 'bloomapp/checkout/payment.html', payment_page_context(order))


def _report_payment_result(request, order, result, payment_id):
    request.session.pop('pending_order_id', None)
    if result == 'refund_due':
        messages.error(request, f'⚠️ Your payment for Order #{order.id} arrived after the order expired. '
                                f'We will refund it — please contact support with payment ID {payment_id}.')
        return redirect('dashboard')
    messages.success(request, 'Payment successful! 🎉 Your order is confirmed.')
    return redirect('order_success', pk=order.id)


@login_required
@require_POST
def confirm_payment(request):
    """
    Called by the payment page after Razorpay reports success.

    The order is looked up by the Razorpay order id that was paid, and the
    signature proves that exact Razorpay order was paid. Each Razorpay order is
    created for one of our orders' exact total, so a payment for a cheaper order
    can't be reused to mark a different order as paid.
    """
    payment_id = request.POST.get('razorpay_payment_id', '')
    rzp_order_id = request.POST.get('razorpay_order_id', '')
    signature = request.POST.get('razorpay_signature', '')

    order = Order.objects.filter(user=request.user, razorpay_order_id=rzp_order_id).first() if rzp_order_id else None
    if not order or not payment_id or not signature:
        messages.error(request, 'Something went wrong. Please contact support.')
        return redirect('home')

    if not payments.verify_payment_signature(order.razorpay_order_id, payment_id, signature):
        messages.error(request, '❌ Payment verification failed. Contact support.')
        return redirect('home')

    result = order_service.mark_order_paid(order, payment_id)
    return _report_payment_result(request, order, result, payment_id)


@csrf_exempt
@require_POST
def razorpay_webhook(request):
    """
    Razorpay calls this server-to-server when a payment is captured, so an
    order is confirmed even if the customer closed the browser before the
    redirect. Only requests signed with RAZORPAY_WEBHOOK_SECRET are accepted.
    """
    signature = request.headers.get('X-Razorpay-Signature', '')
    if not payments.verify_webhook_signature(request.body, signature):
        logger.warning('Rejected Razorpay webhook with a bad signature')
        return HttpResponseBadRequest('invalid signature')

    try:
        event = json.loads(request.body)
        entity = event['payload']['payment']['entity']
    except (ValueError, KeyError, TypeError):
        return HttpResponseBadRequest('unexpected payload')

    event_type = event.get('event')
    order = Order.objects.filter(razorpay_order_id=entity.get('order_id') or '').first()
    if order is None:
        # Not one of ours (or already deleted): acknowledge so Razorpay stops retrying.
        return HttpResponse('ignored')

    if event_type in ('payment.captured', 'order.paid'):
        if int(entity.get('amount', 0)) != payments.amount_in_paise(order.total_amount):
            logger.error('Webhook amount mismatch for order %s', order.id)
            return HttpResponse('amount mismatch')
        order_service.mark_order_paid(order, entity.get('id', ''))
    elif event_type == 'payment.failed':
        logger.info('Payment failed for order %s: %s', order.id, entity.get('error_description'))
    return HttpResponse('ok')
