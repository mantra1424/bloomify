"""Sales report: on-screen, CSV download and printable version (admins only)."""

import csv
from datetime import datetime

from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from django.http import HttpResponse
from django.shortcuts import render

from bloomapp.models import ORDER_STATUS, PAYMENT_MODE, Order, OrderItem
from bloomapp.permissions import admin_role_required

FILTER_KEYS = ('date_from', 'date_to', 'status', 'payment')


def _parse_date(value):
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


def _filters(request):
    return {key: request.GET.get(key, '') for key in FILTER_KEYS}


def report_queryset(filters):
    """Orders matching the report filters."""
    orders = Order.objects.select_related('user', 'coupon').prefetch_related('items__product')
    if date_from := _parse_date(filters['date_from']):
        orders = orders.filter(created_at__date__gte=date_from)
    if date_to := _parse_date(filters['date_to']):
        orders = orders.filter(created_at__date__lte=date_to)
    if filters['status']:
        orders = orders.filter(status=filters['status'])
    if filters['payment']:
        orders = orders.filter(payment_mode=filters['payment'])
    return orders.order_by('-created_at')


def report_context(filters):
    orders = report_queryset(filters)
    # Money totals leave out cancelled orders; the order table still lists them.
    earning = orders.exclude(status='cancelled')
    agg = earning.aggregate(
        total_revenue=Sum('total_amount'),
        total_subtotal=Sum('subtotal'),
        total_discount=Sum('discount_amount'),
        total_delivery=Sum('delivery_charge'),
        total_orders=Count('id'),
    )
    total_revenue = agg['total_revenue'] or 0
    total_orders = agg['total_orders'] or 0
    return {
        'orders': orders,
        'filters': filters,
        'total_revenue': total_revenue,
        'total_subtotal': agg['total_subtotal'] or 0,
        'total_discount': agg['total_discount'] or 0,
        'total_delivery': agg['total_delivery'] or 0,
        'total_orders': total_orders,
        'avg_order_val': round(total_revenue / total_orders, 2) if total_orders else 0,
        'status_breakdown': orders.values('status')
        .annotate(count=Count('id'), revenue=Sum('total_amount'))
        .order_by('-count'),
        'payment_breakdown': earning.values('payment_mode')
        .annotate(count=Count('id'), revenue=Sum('total_amount'))
        .order_by('-count'),
        'top_products': (
            OrderItem.objects.filter(order__in=earning, product__isnull=False)
            .values('product__name')
            .annotate(units_sold=Sum('quantity'), revenue=Sum('line_total'))
            .order_by('-revenue')[:10]
        ),
        'daily': (
            earning.annotate(day=TruncDate('created_at'))
            .values('day')
            .annotate(revenue=Sum('total_amount'), count=Count('id'))
            .order_by('day')
        ),
        'order_statuses': [key for key, _ in ORDER_STATUS],
        'payment_modes': [key for key, _ in PAYMENT_MODE],
    }


@admin_role_required
def admin_sales_report(request):
    context = report_context(_filters(request))
    context['orders'] = context['orders'][:200]  # HTML table is capped; the CSV has every row
    context['admin_user'] = request.admin_user
    return render(request, 'bloomapp/admin_panel/sales_report.html', context)


@admin_role_required
def admin_sales_report_print(request):
    """Print-friendly page; the browser's 'Save as PDF' turns it into a PDF."""
    context = report_context(_filters(request))
    context['admin_user'] = request.admin_user
    return render(request, 'bloomapp/admin_panel/sales_report_print.html', context)


@admin_role_required
def admin_sales_report_csv(request):
    filters = _filters(request)
    orders = report_queryset(filters)
    filename = f'bloomify_sales_{filters["date_from"] or "all"}_to_{filters["date_to"] or "all"}.csv'
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow(
        [
            'Order ID',
            'Date',
            'Customer Name',
            'Email',
            'Phone',
            'City',
            'Pincode',
            'Payment Mode',
            'Status',
            'Subtotal (₹)',
            'Delivery Charge (₹)',
            'Discount (₹)',
            'Total Amount (₹)',
            'Coupon Code',
            'Items',
        ]
    )
    for order in orders:
        items = ' | '.join(
            f'{item.product.name if item.product else "Custom Bouquet"} x{item.quantity}' for item in order.items.all()
        )
        writer.writerow(
            [
                f'#{order.id}',
                order.created_at.strftime('%d-%m-%Y %H:%M'),
                _csv_safe(order.full_name),
                order.email,
                order.phone,
                _csv_safe(order.city),
                order.pincode,
                order.get_payment_mode_display(),
                order.status_display,
                order.subtotal,
                order.delivery_charge,
                order.discount_amount,
                order.total_amount,
                order.coupon.code if order.coupon else '—',
                _csv_safe(items),
            ]
        )
    return response


def _csv_safe(value):
    """Stop spreadsheet apps treating customer text as a formula (CSV injection)."""
    text = str(value)
    return f"'{text}" if text[:1] in ('=', '+', '-', '@') else text
