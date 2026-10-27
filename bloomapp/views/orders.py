"""Customer order pages: confirmation, tracking and cancellation."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from bloomapp.models import Order
from bloomapp.services import orders as order_service

TRACKING_STEPS = [
    ('placed', 'Order Placed', 'Your order has been confirmed.'),
    ('packed', 'Packed', 'Your bouquet is being carefully packed.'),
    ('out_for_delivery', 'Out for Delivery', 'On the way to you!'),
    ('delivered', 'Delivered', 'Enjoy your beautiful flowers! 🌸'),
]


@login_required
def order_success(request, pk):
    order = get_object_or_404(Order.objects.prefetch_related('items__product'), pk=pk, user=request.user)
    return render(request, 'bloomapp/orders/success.html', {'order': order})


@login_required
def order_tracking(request, pk):
    order = get_object_or_404(Order, pk=pk, user=request.user)
    return render(
        request,
        'bloomapp/orders/tracking.html',
        {
            'order': order,
            'items': order.items.select_related('product', 'custom_bouquet'),
            'steps': TRACKING_STEPS,
        },
    )


@login_required
@require_POST
def cancel_order(request, pk):
    order = get_object_or_404(Order, pk=pk, user=request.user)
    if order.status != 'placed':
        messages.error(request, 'Only orders with status “Placed” can be cancelled.')
        return redirect('dashboard')
    order_service.cancel_order(order)
    messages.success(request, f'Order #{order.id} has been cancelled. Stock restored.')
    return redirect('dashboard')
