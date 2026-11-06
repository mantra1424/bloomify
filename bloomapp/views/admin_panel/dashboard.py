"""Admin dashboard, analytics API, users list and contact messages."""

from datetime import timedelta

from django.contrib import messages
from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from bloomapp.models import Category, ContactMessage, Order, OrderItem, Product, User
from bloomapp.permissions import admin_role_required, staff_required
from bloomapp.services import emails
from bloomapp.services.orders import release_expired_online_orders


def revenue_orders():
    """Orders that count towards revenue (cancelled orders never do)."""
    return Order.objects.exclude(status='cancelled')


@staff_required
def admin_dashboard(request):
    release_expired_online_orders()
    admin_user = request.admin_user
    is_staff = not admin_user.is_admin()
    by_status = dict(Order.objects.values_list('status').annotate(n=Count('id')))

    return render(
        request,
        'bloomapp/admin_panel/dashboard.html',
        {
            'admin_user': admin_user,
            'is_staff': is_staff,
            'total_orders': sum(by_status.values()),
            'pending_orders': by_status.get('placed', 0),
            'packed_orders': by_status.get('packed', 0),
            'out_orders': by_status.get('out_for_delivery', 0),
            'recent_orders': Order.objects.order_by('-created_at')[:5],
            # Staff only see order counts, not revenue or user numbers.
            'total_users': None if is_staff else User.objects.filter(role='user').count(),
            'total_revenue': None if is_staff else (revenue_orders().aggregate(r=Sum('total_amount'))['r'] or 0),
            'out_of_stock': Product.objects.filter(status='available', stock_quantity=0).order_by('name'),
            'low_stock': Product.objects.filter(
                status='available', stock_quantity__gt=0, stock_quantity__lte=5
            ).order_by('stock_quantity'),
        },
    )


@admin_role_required
def admin_analytics_api(request):
    """Chart data for the dashboard: last 7 days of revenue and sign-ups, orders per category."""
    today = timezone.localdate()
    days = [today - timedelta(days=i) for i in range(6, -1, -1)]
    start = days[0]

    revenue_by_day = dict(
        revenue_orders()
        .filter(created_at__date__gte=start)
        .annotate(day=TruncDate('created_at'))
        .values_list('day')
        .annotate(total=Sum('total_amount'))
    )
    signups_by_day = dict(
        User.objects.filter(created_at__date__gte=start)
        .annotate(day=TruncDate('created_at'))
        .values_list('day')
        .annotate(n=Count('id'))
    )
    per_category = dict(OrderItem.objects.values_list('product__category_id').annotate(n=Count('id')))
    categories = Category.objects.filter(status='available')
    labels = [d.strftime('%d %b') for d in days]

    return JsonResponse(
        {
            'revenue': {'labels': labels, 'data': [float(revenue_by_day.get(d, 0)) for d in days]},
            'categories': {
                'labels': [c.name for c in categories],
                'data': [per_category.get(c.id, 0) for c in categories],
            },
            'signups': {'labels': labels, 'data': [signups_by_day.get(d, 0) for d in days]},
        }
    )


@admin_role_required
def admin_users(request):
    users = User.objects.order_by('-created_at')
    return render(
        request,
        'bloomapp/admin_panel/users.html',
        {
            'admin_user': request.admin_user,
            'users': users,
            'staff_count': users.filter(role__in=['admin', 'staff']).count(),
        },
    )


REPLY_MAX_LENGTH = 5000


@staff_required
def admin_messages(request):
    if request.method == 'POST':
        msg_id = request.POST.get('msg_id', '')
        if not msg_id.isdigit():
            raise Http404
        msg = get_object_or_404(ContactMessage, pk=msg_id)
        if request.POST.get('action') == 'reply':
            _send_reply(request, msg)
        else:
            ContactMessage.objects.filter(pk=msg.pk).update(is_read=True)
        return redirect(f'{reverse("admin_messages")}?open={msg.pk}#msg-{msg.pk}')

    msgs = ContactMessage.objects.select_related('replied_by')
    return render(
        request,
        'bloomapp/admin_panel/messages.html',
        {
            'admin_user': request.admin_user,
            'is_staff': not request.admin_user.is_admin(),
            'messages_list': msgs,
            'unread_count': msgs.filter(is_read=False).count(),
            'needs_reply_count': msgs.filter(replied_at__isnull=True).count(),
            'open_id': request.GET.get('open', ''),
            'reply_max_length': REPLY_MAX_LENGTH,
        },
    )


def _send_reply(request, msg):
    reply = request.POST.get('reply', '').strip()
    if msg.is_replied:
        messages.info(request, f'{msg.name} has already been answered.')
    elif not reply:
        messages.error(request, 'Write a reply before sending.')
    elif len(reply) > REPLY_MAX_LENGTH:
        messages.error(request, f'Replies can be up to {REPLY_MAX_LENGTH} characters.')
    elif not emails.send_contact_reply(msg, reply, request.admin_user.full_name):
        messages.error(request, 'The email could not be sent. Check the email settings and try again.')
    else:
        msg.reply, msg.replied_at, msg.replied_by, msg.is_read = reply, timezone.now(), request.admin_user, True
        msg.save(update_fields=['reply', 'replied_at', 'replied_by', 'is_read'])
        messages.success(request, f'Reply sent to {msg.email}.')
