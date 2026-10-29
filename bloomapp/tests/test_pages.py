import io
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


def test_photo_credits_page_lists_every_demo_photo(client):
    response = client.get(reverse('photo_credits'))
    assert response.status_code == 200
    credits = response.context['credits']
    assert len(credits) == 12
    assert all(
        c['license'] and c['author'] and c['source'].startswith('https://commons.wikimedia.org/') for c in credits
    )


def test_every_credited_photo_file_exists():
    from django.contrib.staticfiles import finders

    from bloomapp.views.pages import _photo_credits

    assert all(finders.find(c['file']) for c in _photo_credits())


@pytest.mark.parametrize(
    ('image_url', 'expected'),
    [
        ('', '/static/bloomapp/img/placeholder-bouquet.svg'),
        ('bloomapp/demo/products/lavender-love.jpg', '/static/bloomapp/demo/products/lavender-love.jpg'),
        ('https://example.com/rose.jpg', 'https://example.com/rose.jpg'),
    ],
)
def test_product_image_sources(product, image_url, expected):
    product.image_url = image_url
    assert product.get_image == expected


def test_seed_data_gives_every_product_a_photo(db):
    from django.contrib.staticfiles import finders
    from django.core.management import call_command

    from bloomapp.models import Product

    call_command('seed_data', stdout=io.StringIO())
    products = list(Product.objects.all())
    assert len(products) == 12
    for p in products:
        assert p.image_url and finders.find(p.image_url), p.name

    # Running it again on an older database fills in missing photos without duplicates.
    Product.objects.update(image_url='')
    call_command('seed_data', stdout=io.StringIO())
    assert Product.objects.count() == 12
    assert not Product.objects.filter(image_url='').exists()


def test_pincode_check_endpoint(client):
    ok = client.get(reverse('check_pincode'), {'pincode': '390001'}).json()
    assert ok['ok'] is True
    assert ok['city'] == 'Vadodara'
    nope = client.get(reverse('check_pincode'), {'pincode': '400001'}).json()
    assert nope['ok'] is False
    assert 'Anand' in nope['message']


@pytest.mark.parametrize(
    ('value', 'expected'),
    [(1299, '₹1,299'), ('999.00', '₹999'), ('1299.50', '₹1,299.50'), (0, '₹0'), (None, ''), ('abc', '')],
)
def test_rupees_filter(value, expected):
    from bloomapp.templatetags.bloom import rupees

    assert rupees(value) == expected


def test_home_page_shows_occasions_bestsellers_and_no_fake_reviews(client, product):
    response = client.get(reverse('home'))
    html = response.content.decode()
    assert response.context['occasions'][0]['category'] == product.category
    assert product in response.context['bestsellers']
    assert '₹700' in html and '₹800' in html  # formatted prices, no ".00"
    assert 'Loved by Thousands' not in html
    assert 'data-pin-check' in html


def test_product_card_hides_stars_without_reviews(client, product):
    html = client.get(reverse('home')).content.decode()
    assert 'product-card-rating' not in html


def test_sold_out_product_cannot_be_added_from_card(client, product):
    product.stock_quantity = 0
    product.save()
    html = client.get(reverse('home')).content.decode()
    assert 'Sold out' in html
    assert 'is sold out' in html
