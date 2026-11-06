"""The demo site's sample customers, orders and reviews (created by seed_data)."""

import io
from datetime import timedelta

import pytest
from django.core.management import call_command
from django.db.models import F
from django.urls import reverse
from django.utils import timezone

from bloomapp.models import ContactMessage, Order, Payment, Review, SavedAddress, User, Wishlist

pytestmark = pytest.mark.django_db


def seed(*args):
    out = io.StringIO()
    call_command('seed_data', *args, stdout=out)
    return out.getvalue()


def sample_orders():
    return Order.objects.filter(user__email__endswith='@example.com')


def test_seed_creates_sample_activity_once():
    seed()
    counts = (sample_orders().count(), Review.objects.count(), ContactMessage.objects.count())
    assert counts[0] > 20 and counts[1] >= 24 and counts[2] == 3

    assert 'already exists' in seed()
    assert (sample_orders().count(), Review.objects.count(), ContactMessage.objects.count()) == counts


def test_sample_orders_cover_every_stage_with_matching_payments():
    seed()
    statuses = set(sample_orders().values_list('status', flat=True))
    assert {'placed', 'packed', 'delivered'} <= statuses
    for order in sample_orders().select_related('payment'):
        assert order.total_amount == order.subtotal + order.delivery_charge
        if order.status == 'cancelled':
            assert order.payment.status == 'cancelled'
        if order.status == 'delivered':
            assert order.is_paid
    # Nobody signs in as a sample customer, and none ordered before signing up.
    for user in User.objects.filter(email__endswith='@example.com'):
        assert not user.has_usable_password()
        first = Order.objects.filter(user=user).order_by('created_at').first()
        assert first is None or first.created_at >= user.created_at


def test_demo_customer_has_orders_address_and_wishlist(client):
    seed()
    demo = User.objects.get(email='demo@bloomify.com')
    client.force_login(demo)
    page = client.get(reverse('dashboard')).context
    assert len(page['orders']) == 3
    assert SavedAddress.objects.filter(user=demo).exists()
    assert Wishlist.objects.filter(user=demo).count() == 3


def test_old_sample_data_moves_forward_to_today():
    seed()
    sample_orders().update(created_at=F('created_at') - timedelta(days=10))
    assert 'moved forward 10 days' in seed()
    newest = sample_orders().order_by('-created_at').first()
    assert timezone.localtime(newest.created_at).date() == timezone.localdate()


def test_seed_can_skip_sample_activity():
    seed('--no-activity')
    assert not Order.objects.exists() and not Payment.objects.exists()


def test_one_sample_message_is_already_answered():
    seed()
    assert ContactMessage.objects.filter(replied_at__isnull=False).count() == 1
    assert ContactMessage.objects.filter(replied_at__isnull=True).count() == 2
