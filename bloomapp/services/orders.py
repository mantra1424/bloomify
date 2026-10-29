"""Placing, paying, cancelling and releasing orders."""

import logging
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from bloomapp.models import (
    Coupon,
    DeliverySlot,
    DeliveryZone,
    Order,
    OrderItem,
    Payment,
    Product,
)
from bloomapp.services import emails, payments, pricing

logger = logging.getLogger(__name__)

ONLINE_PAYMENT_MODES = ('online', 'upi', 'card')


class OutOfStock(Exception):
    def __init__(self, product):
        super().__init__(f'{product.name} is out of stock')
        self.product = product


class PaymentStartError(Exception):
    """Razorpay could not create a payment order."""


@dataclass
class CheckoutDetails:
    full_name: str
    email: str
    phone: str
    address: str
    city: str
    state: str
    pincode: str
    payment_mode: str
    delivery_type: str = 'normal'
    distance_km: float = 3.0
    coupon_code: str = ''
    slot_id: int | None = None
    special_note: str = ''


def find_zone(pincode):
    for prefix_len in (6, 5, 4, 3):
        zone = DeliveryZone.objects.filter(pincode_prefix=pincode[:prefix_len]).first()
        if zone:
            return zone
    return None


def _claim_coupon(code):
    """Use up one coupon redemption if it is still valid. Returns the coupon or None."""
    if not code:
        return None
    coupon = Coupon.objects.filter(code=code.strip().upper()).first()
    if (
        coupon
        and coupon.is_valid
        and Coupon.objects.filter(pk=coupon.pk, used_count__lt=F('max_uses')).update(used_count=F('used_count') + 1)
    ):
        return coupon
    return None


def _book_slot(slot_id):
    if not slot_id:
        return None
    slot = DeliverySlot.objects.filter(id=slot_id).first()
    if slot is None or slot.has_started:
        return None
    if DeliverySlot.objects.filter(pk=slot.pk, booked_count__lt=F('max_orders')).update(
        booked_count=F('booked_count') + 1
    ):
        return slot
    return None


def place_order(user, cart_items, details: CheckoutDetails):
    """
    Turn a cart into an order.

    Everything happens in one transaction, so a failure never leaves a
    half-made order or stock that was taken but not sold. COD orders are
    confirmed straight away; online orders also get a Razorpay order to pay.

    Raises OutOfStock or PaymentStartError.
    """
    cart_items = list(cart_items)
    subtotal = sum((item.subtotal for item in cart_items), Decimal('0'))
    delivery = pricing.calc_delivery(details.city, details.distance_km, details.delivery_type, float(subtotal))
    delivery_charge = Decimal(delivery['delivery_charge'])

    with transaction.atomic():
        coupon = _claim_coupon(details.coupon_code)
        discount = pricing.coupon_discount(subtotal, coupon) if coupon else Decimal('0')
        order = Order.objects.create(
            user=user,
            full_name=details.full_name,
            email=details.email,
            phone=details.phone,
            address=details.address,
            city=details.city,
            state=details.state,
            pincode=details.pincode,
            delivery_zone=find_zone(details.pincode),
            delivery_charge=delivery_charge,
            coupon=coupon,
            discount_amount=discount,
            subtotal=subtotal,
            total_amount=subtotal + delivery_charge - discount,
            payment_mode=details.payment_mode,
            delivery_slot=_book_slot(details.slot_id),
            special_note=details.special_note,
            status='placed',
        )
        for item in cart_items:
            OrderItem.objects.create(
                order=order,
                product=item.product,
                custom_bouquet=item.custom_bouquet,
                quantity=item.quantity,
                price=item.unit_price,
                line_total=item.subtotal,
            )
            # Take stock only if enough is left right now (safe if two people buy at once).
            if item.product and not Product.objects.filter(
                pk=item.product.pk, stock_quantity__gte=item.quantity
            ).update(stock_quantity=F('stock_quantity') - item.quantity):
                raise OutOfStock(item.product)

        is_online = details.payment_mode in ONLINE_PAYMENT_MODES
        Payment.objects.create(
            order=order,
            user=user,
            amount=order.total_amount,
            mode=details.payment_mode,
            status='pending' if is_online else 'cod_pending',
        )
        for item in cart_items:
            item.delete()

    if not is_online:
        emails.send_order_confirmation_email(order)
        return order

    try:
        order.razorpay_order_id = payments.create_razorpay_order(order)
    except Exception as exc:
        logger.exception('Razorpay order creation failed for order %s', order.id)
        release_order(order, payment_status='failed')
        raise PaymentStartError(str(exc)) from exc
    order.save(update_fields=['razorpay_order_id', 'updated_at'])
    return order


def mark_order_paid(order, razorpay_payment_id):
    """
    Record a verified online payment. Safe to call twice (browser redirect and
    webhook can both arrive). Returns 'paid', 'already_paid' or 'refund_due'.
    """
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order.pk)
        payment = Payment.objects.select_for_update().filter(order=order).first()
        if payment is None:
            payment = Payment(order=order, user=order.user, amount=order.total_amount, mode=order.payment_mode)
        if payment.status in ('completed', 'refund_due'):
            return 'already_paid'
        payment.transaction_id = razorpay_payment_id
        # Paid after the order already expired or was cancelled: money must go back.
        payment.status = 'refund_due' if order.status == 'cancelled' else 'completed'
        payment.save()
    if payment.status == 'refund_due':
        logger.warning('Payment %s arrived for cancelled order %s — refund needed', razorpay_payment_id, order.id)
        return 'refund_due'
    emails.send_order_confirmation_email(order)
    return 'paid'


def release_order(order, payment_status=None):
    """Cancel an order and give back its stock, coupon use and delivery slot."""
    with transaction.atomic():
        # Re-read and lock so two requests can't release the same order twice.
        order = Order.objects.select_for_update().get(pk=order.pk)
        if order.status == 'cancelled':
            return False
        for item in order.items.all():
            if item.product_id:
                Product.objects.filter(pk=item.product_id).update(stock_quantity=F('stock_quantity') + item.quantity)
        if order.coupon_id:
            Coupon.objects.filter(pk=order.coupon_id, used_count__gt=0).update(used_count=F('used_count') - 1)
        if order.delivery_slot_id:
            DeliverySlot.objects.filter(pk=order.delivery_slot_id, booked_count__gt=0).update(
                booked_count=F('booked_count') - 1
            )
        order.status = 'cancelled'
        order.save(update_fields=['status', 'updated_at'])
        if payment_status:
            Payment.objects.filter(order=order).update(status=payment_status)
    return True


def cancel_order(order):
    """Customer or admin cancellation, with the right payment status afterwards."""
    payment = Payment.objects.filter(order=order).first()
    new_status = None
    if payment and payment.status == 'pending':
        new_status = 'cancelled'
    elif payment and payment.status == 'completed':
        new_status = 'refund_due'
    return release_order(order, payment_status=new_status)


def release_expired_online_orders():
    """Cancel online orders whose payment never finished, so their stock comes back."""
    timeout = getattr(settings, 'PENDING_PAYMENT_TIMEOUT_MINUTES', 30)
    cutoff = timezone.now() - timedelta(minutes=timeout)
    expired = Order.objects.filter(
        status='placed',
        payment_mode__in=ONLINE_PAYMENT_MODES,
        payment__status='pending',
        created_at__lt=cutoff,
    )
    released = 0
    for order in expired:
        if release_order(order, payment_status='expired'):
            released += 1
    return released
