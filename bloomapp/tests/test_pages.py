import json
from datetime import date, timedelta

import pytest
from django.urls import reverse

from bloomapp.models import ContactMessage, DeliverySlot, NewsletterSubscriber, Wishlist

pytestmark = pytest.mark.django_db

PUBLIC_PAGES = ['home', 'products', 'contact', 'faqs', 'returns', 'login', 'signup', 'password_reset', 'admin_login']
CUSTOMER_PAGES = ['cart', 'wishlist', 'dashboard', 'custom_bouquet']


@pytest.mark.parametrize('name', PUBLIC_PAGES)
def test_public_pages_load(client, product, name):
    assert client.get(reverse(name)).status_code == 200


@pytest.mark.parametrize('name', CUSTOMER_PAGES)
def test_customer_pages_load(customer_client, name):
    assert customer_client.get(reverse(name)).status_code == 200


def test_product_detail_and_filters(client, product):
    assert client.get(reverse('product_detail', args=[product.id])).status_code == 200
    response = client.get(reverse('products'), {'q': 'rose', 'min_price': 'abc', 'sort': 'price_desc'})
    assert response.status_code == 200
    assert product in response.context['products']


def test_healthz(client):
    response = client.get(reverse('healthz'))
    assert response.status_code == 200
    assert response.json() == {'status': 'ok'}


def test_contact_form_saves_message(client):
    client.post(
        reverse('contact'),
        {'name': 'Riya', 'email': 'riya@example.com', 'subject': 'Order', 'message': 'Hello!'},
    )
    assert ContactMessage.objects.filter(email='riya@example.com').exists()


def test_newsletter_validates_email(client):
    assert client.post(reverse('newsletter_subscribe'), {'email': 'not-an-email@'}).status_code == 400
    assert client.post(reverse('newsletter_subscribe'), {'email': 'Fan@Example.com'}).json()['ok']
    assert NewsletterSubscriber.objects.filter(email='fan@example.com').exists()


def test_search_autocomplete(client, product):
    assert client.get(reverse('search_autocomplete'), {'q': 'r'}).json() == {'results': []}
    results = client.get(reverse('search_autocomplete'), {'q': 'Roses'}).json()['results']
    assert results[0]['url'] == reverse('product_detail', args=[product.id])


def test_wishlist_toggle(customer_client, customer, product):
    url = reverse('toggle_wishlist', args=[product.id])
    ajax = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}
    assert customer_client.post(url, **ajax).json()['in_wishlist'] is True
    assert Wishlist.objects.filter(user=customer, product=product).exists()
    assert customer_client.post(url, **ajax).json()['in_wishlist'] is False


def test_delivery_slots_only_for_the_booking_window(client):
    today = date.today()
    slots = client.get(reverse('get_slots'), {'date': today.isoformat()}).json()['slots']
    assert len(slots) == 5
    far = today + timedelta(days=60)
    assert client.get(reverse('get_slots'), {'date': far.isoformat()}).json() == {'slots': []}
    assert not DeliverySlot.objects.filter(date=far).exists()


def test_calculate_delivery_api(client):
    url = reverse('calculate_delivery')
    ok = client.post(url, json.dumps({'city': 'Anand', 'subtotal': 1200}), content_type='application/json')
    assert ok.json()['is_free'] is True
    nope = client.post(url, json.dumps({'city': 'Mumbai'}), content_type='application/json')
    assert nope.status_code == 422
    bad = client.post(url, 'not json', content_type='application/json')
    assert bad.status_code == 400
