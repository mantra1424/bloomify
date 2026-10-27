"""Checkout page, its AJAX helpers, and placing the order."""
import json
from datetime import date, datetime, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST

from bloomapp.forms import CheckoutForm, first_error
from bloomapp.models import Coupon, DeliverySlot, DeliveryZone, SavedAddress
from bloomapp.services import orders as order_service
from bloomapp.services import pricing
from bloomapp.utils import parse_float
from bloomapp.views.cart import cart_items_for
from bloomapp.views.payments import payment_page_context

BOOKING_WINDOW_DAYS = 7
DEFAULT_SLOTS = [
    ('9 AM – 11 AM', '09:00', '11:00'),
    ('11 AM – 1 PM', '11:00', '13:00'),
    ('1 PM – 3 PM', '13:00', '15:00'),
    ('3 PM – 6 PM', '15:00', '18:00'),
    ('6 PM – 9 PM', '18:00', '21:00'),
]


@login_required
def checkout_view(request):
    items = cart_items_for(request.user)
    if not items.exists():
        messages.warning(request, 'Your cart is empty.')
        return redirect('cart')
    today = date.today()
    return render(request, 'bloomapp/checkout/checkout.html', {
        'items': items,
        'subtotal': sum(item.subtotal for item in items),
        'addresses': SavedAddress.objects.filter(user=request.user),
        'available_dates': [today + timedelta(days=i) for i in range(BOOKING_WINDOW_DAYS)],
        'delivery_cities': pricing.DELIVERY_CITIES,
        'delivery_config': {
            'cities': pricing.DELIVERY_CITIES,
            'time_charges': pricing.TIME_CHARGES,
        },
    })


@require_GET
def get_slots_ajax(request):
    """Delivery slots for one date in the booking window (created on first request)."""
    try:
        day = datetime.strptime(request.GET.get('date') or '', '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'slots': []})
    today = date.today()
    if not today <= day < today + timedelta(days=BOOKING_WINDOW_DAYS):
        return JsonResponse({'slots': []})

    if not DeliverySlot.objects.filter(date=day).exists():
        DeliverySlot.objects.bulk_create([
            DeliverySlot(date=day, slot_label=label, slot_start=start, slot_end=end, max_orders=10)
            for label, start, end in DEFAULT_SLOTS
        ])
    slots = DeliverySlot.objects.filter(date=day).order_by('slot_start')
    return JsonResponse({'slots': [{
        'id': s.id, 'label': s.slot_label, 'available': s.is_available, 'slots_left': s.slots_left,
    } for s in slots]})


@require_GET
def get_delivery_charge_ajax(request):
    """Delivery zone and charge for a pincode."""
    pincode = request.GET.get('pincode', '')
    zone = order_service.find_zone(pincode) if pincode.isdigit() else None
    if zone:
        return JsonResponse({'charge': float(zone.delivery_charge), 'zone': zone.zone_name})
    return JsonResponse({'charge': 60.0, 'zone': 'Standard'})


@require_POST
def calculate_delivery_api(request):
    try:
        data = json.loads(request.body)
        city = str(data.get('city', '')).strip()
        distance_km = parse_float(data.get('distance_km', 3), 3.0, min_value=0, max_value=500)
        delivery_type = str(data.get('delivery_type', 'normal'))
        subtotal = parse_float(data.get('subtotal', 0), 0.0, min_value=0)
    except (ValueError, AttributeError, TypeError):
        return JsonResponse({'error': 'Invalid input'}, status=400)
    if not pricing.is_serviceable(city):
        return JsonResponse({'error': 'City not serviceable'}, status=422)
    return JsonResponse(pricing.calc_delivery(city, distance_km, delivery_type, subtotal))


@require_GET
def apply_coupon_ajax(request):
    """Preview a coupon's discount for the current cart (it is claimed only at order time)."""
    if not request.user.is_authenticated:
        return JsonResponse({'valid': False, 'message': 'Login required'})
    code = request.GET.get('code', '').strip().upper()
    coupon = Coupon.objects.filter(code=code).first()
    if coupon is None:
        return JsonResponse({'valid': False, 'message': 'Invalid coupon code.'})
    if not coupon.is_valid:
        return JsonResponse({'valid': False, 'message': 'Coupon expired or usage limit reached.'})
    subtotal = sum(item.subtotal for item in cart_items_for(request.user))
    return JsonResponse({
        'valid': True,
        'discount_percent': coupon.discount_percent,
        'discount_amount': float(pricing.coupon_discount(subtotal, coupon)),
        'message': f'{coupon.discount_percent}% off applied!',
    })


@login_required
@require_POST
def place_order(request):
    order_service.release_expired_online_orders()
    items = list(cart_items_for(request.user))
    if not items:
        return redirect('cart')

    form = CheckoutForm(request.POST)
    if not form.is_valid():
        messages.error(request, f'❌ {first_error(form)}')
        return redirect('checkout')

    for item in items:
        if item.product and item.product.stock_quantity < item.quantity:
            messages.error(request, f'❌ "{item.product.name}" only has {item.product.stock_quantity} left in stock. '
                                    'Please update your cart.')
            return redirect('cart')

    try:
        order = order_service.place_order(request.user, items, form.to_details())
    except order_service.OutOfStock as exc:
        messages.error(request, f'❌ "{exc.product.name}" just sold out. Please update your cart.')
        return redirect('cart')
    except order_service.PaymentStartError:
        messages.error(request, '❌ Could not start online payment. Please try again or choose Cash on Delivery.')
        return redirect('cart')

    if order.payment_mode not in order_service.ONLINE_PAYMENT_MODES:
        messages.success(request, 'Order placed successfully! 🌸')
        return redirect('order_success', pk=order.id)

    request.session['pending_order_id'] = order.id
    return render(request, 'bloomapp/checkout/payment.html', payment_page_context(order))
