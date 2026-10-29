"""Phase 5 polish: forms keep what people typed, pages show live data, honest order wording."""

import pytest
from django.urls import reverse

from bloomapp.models import ContactMessage, Order, Payment, SavedAddress, Wishlist
from bloomapp.services import pricing

pytestmark = pytest.mark.django_db


def make_order(user, **extra):
    fields = {
        'user': user,
        'full_name': 'Test Buyer',
        'phone': '9876543210',
        'email': user.email,
        'address': 'Shop 12 Main Road',
        'city': 'Anand',
        'state': 'Gujarat',
        'pincode': '388001',
        'subtotal': 500,
        'delivery_charge': 20,
        'total_amount': 520,
        **extra,
    }
    return Order.objects.create(**fields)


# ── Sign up and log in ─────────────────────────────────────────────────────
def test_signup_error_keeps_what_was_typed(client):
    res = client.post(
        reverse('signup'),
        {'full_name': 'Riya Shah', 'email': 'riya@example.com', 'password': 'abc', 'confirm_password': 'abc'},
    )
    assert res.status_code == 200
    assert b'value="Riya Shah"' in res.content
    assert b'value="riya@example.com"' in res.content
    assert b'too short' in res.content


def test_signup_follows_safe_next(client):
    data = {
        'full_name': 'Riya Shah',
        'email': 'riya@example.com',
        'password': 'Tulips-in-bloom-9',
        'confirm_password': 'Tulips-in-bloom-9',
    }
    res = client.post(reverse('signup') + '?next=/checkout/', data)
    assert res['Location'] == '/checkout/'


def test_failed_login_keeps_email_and_shows_error_inline(client, customer):
    res = client.post(reverse('login'), {'email': customer.email, 'password': 'wrong'})
    assert res.status_code == 200
    assert res.context['email'] == customer.email
    assert b'Incorrect email or password.' in res.content


# ── Account ────────────────────────────────────────────────────────────────
def test_saving_an_address_returns_to_the_addresses_tab(customer_client, customer):
    res = customer_client.post(
        reverse('dashboard'),
        {
            'action': 'add_address',
            'label': 'Home',
            'addr_name': 'Test Buyer',
            'addr_phone': '9876543210',
            'addr_street': 'B-12, Station Road',
            'addr_city': 'Anand',
            'addr_state': 'Gujarat',
            'addr_pincode': '388001',
        },
    )
    assert res['Location'].endswith('?tab=addresses')
    assert SavedAddress.objects.filter(user=customer).count() == 1


def test_profile_update_returns_to_the_profile_tab(customer_client):
    res = customer_client.post(reverse('dashboard'), {'action': 'update_profile', 'full_name': 'New Name'})
    assert res['Location'].endswith('?tab=profile')


def test_unknown_dashboard_tab_falls_back_to_orders(customer_client):
    assert customer_client.get(reverse('dashboard') + '?tab=nope').context['tab'] == 'orders'


def test_wishlist_page_lists_saved_bouquets(customer_client, customer, product):
    Wishlist.objects.create(user=customer, product=product)
    res = customer_client.get(reverse('wishlist'))
    assert [p.pk for p in res.context['products']] == [product.pk]
    assert product.pk in res.context['wishlist_ids']


# ── Orders ─────────────────────────────────────────────────────────────────
def test_tracking_says_pay_on_delivery_for_cod(customer_client, customer):
    order = make_order(customer, payment_mode='cod')
    res = customer_client.get(reverse('order_tracking', args=[order.pk]))
    assert b'To pay on delivery' in res.content
    assert b'Total paid' not in res.content


def test_tracking_only_says_paid_once_payment_completed(customer_client, customer):
    order = make_order(customer, payment_mode='online')
    Payment.objects.create(order=order, user=customer, amount=520, mode='online', status='pending')
    res = customer_client.get(reverse('order_tracking', args=[order.pk]))
    assert b'Online payment not completed' in res.content
    assert not order.is_paid

    order.payment.status = 'completed'
    order.payment.save()
    order.refresh_from_db()
    assert order.is_paid
    assert b'Total paid' in customer_client.get(reverse('order_tracking', args=[order.pk])).content


def test_cancelled_order_shows_cancelled_notice_not_progress(customer_client, customer):
    order = make_order(customer, status='cancelled')
    res = customer_client.get(reverse('order_tracking', args=[order.pk]))
    assert b'This order was cancelled.' in res.content
    assert b'class="timeline"' not in res.content


# ── Help pages ─────────────────────────────────────────────────────────────
def test_contact_form_redirects_after_sending(client):
    res = client.post(
        reverse('contact'),
        {'name': 'Riya', 'email': 'riya@example.com', 'subject': 'Delivery', 'message': 'Hello'},
    )
    assert res.status_code == 302 and res['Location'].endswith('?sent=1')
    assert ContactMessage.objects.count() == 1
    assert client.get(res['Location']).context['sent'] is True


def test_contact_form_error_keeps_message(client):
    res = client.post(reverse('contact'), {'name': 'Riya', 'email': 'not-an-email', 'message': 'Keep me'})
    assert res.status_code == 200
    assert b'Keep me' in res.content
    assert ContactMessage.objects.count() == 0


def test_faq_uses_live_delivery_prices(client):
    res = client.get(reverse('faqs'))
    for city in pricing.DELIVERY_CITIES.values():
        assert city['name'].encode() in res.content
    assert b'Vapi' not in res.content


def test_bouquet_builder_offers_every_flower_and_wrapping(customer_client):
    res = customer_client.get(reverse('custom_bouquet'))
    assert [f['key'] for f in res.context['flower_options']] == list(pricing.FLOWER_SURCHARGES)
    assert [w['key'] for w in res.context['wrap_options']] == list(pricing.WRAPPING_COSTS)
