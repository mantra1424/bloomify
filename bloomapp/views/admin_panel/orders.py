"""Admin order list and status updates (staff and admins)."""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from bloomapp.models import ORDER_STATUS, Order
from bloomapp.permissions import staff_required
from bloomapp.services import orders as order_service


@staff_required
def admin_orders(request):
    order_service.release_expired_online_orders()
    orders = (
        Order.objects.select_related('user', 'delivery_slot', 'payment')
        .prefetch_related('items__product', 'items__custom_bouquet')
        .order_by('-created_at')
    )
    status_filter = request.GET.get('status', '')
    if status_filter:
        orders = orders.filter(status=status_filter)
    return render(
        request,
        'bloomapp/admin_panel/orders.html',
        {
            'admin_user': request.admin_user,
            'orders': orders,
            'status_choices': ORDER_STATUS,
            'status_filter': status_filter,
            'is_staff': not request.admin_user.is_admin(),
        },
    )


@staff_required
@require_POST
def admin_order_update(request, pk):
    order = get_object_or_404(Order, pk=pk)
    new_status = request.POST.get('status', '')
    if new_status not in dict(ORDER_STATUS):
        messages.error(request, 'Unknown order status.')
    elif order.status == 'cancelled':
        messages.error(request, f'Order #{order.id} is cancelled and can no longer change.')
    elif new_status == 'cancelled':
        # Go through the service so stock, coupon and slot are given back.
        order_service.cancel_order(order)
        messages.success(request, f'Order #{order.id} cancelled. Stock restored.')
    else:
        order.status = new_status
        order.save(update_fields=['status', 'updated_at'])
        messages.success(request, f'Order #{order.id} status updated.')
    return redirect('admin_orders')
