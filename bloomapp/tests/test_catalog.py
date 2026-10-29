"""Shop page filters/sorting and the product page."""

import pytest
from django.urls import reverse

from bloomapp.models import Category, Product, Review

pytestmark = pytest.mark.django_db


@pytest.fixture
def catalog(category):
    other = Category.objects.create(name='Wedding', slug='wedding')

    def make(name, price, flowers, cat=category, **kw):
        return Product.objects.create(
            name=name, category=cat, original_price=price, price=price, stock_quantity=5, flowers=flowers, **kw
        )

    return {
        'cheap_rose': make('Cheap Roses', 500, 'Red Roses'),
        'mid_lily': make('Mid Lilies', 1500, 'lily rose'),
        'big_orchid': make('Big Orchids', 3000, 'orchid', cat=other),
        'sold_out': make('Gone Tulips', 800, 'tulip'),
    }


def names(response):
    return [p.name for p in response.context['products']]


def test_price_bands(client, catalog):
    url = reverse('products')
    assert set(names(client.get(url, {'price': 'under-1000'}))) == {'Cheap Roses', 'Gone Tulips'}
    assert names(client.get(url, {'price': '1000-2000'})) == ['Mid Lilies']
    assert names(client.get(url, {'price': 'over-2000'})) == ['Big Orchids']
    # An unknown band is ignored rather than breaking the page.
    assert len(names(client.get(url, {'price': 'free'}))) == 4


def test_flower_filter_matches_its_count(client, catalog):
    response = client.get(reverse('products'), {'flower': 'rose'})
    counts = {f['key']: f['count'] for f in response.context['flower_options']}
    assert set(names(response)) == {'Cheap Roses', 'Mid Lilies'}
    assert counts['rose'] == len(names(response)) == 2
    assert counts['orchid'] == 1


def test_flower_counts_follow_other_filters(client, catalog):
    response = client.get(reverse('products'), {'category': 'wedding'})
    counts = {f['key']: f['count'] for f in response.context['flower_options']}
    assert counts == {'rose': 0, 'lily': 0, 'tulip': 0, 'sunflower': 0, 'orchid': 1}


def test_several_flowers_combine_with_or(client, catalog):
    response = client.get(reverse('products'), {'flower': ['orchid', 'tulip']})
    assert set(names(response)) == {'Big Orchids', 'Gone Tulips'}
    assert response.context['active_filter_count'] == 2


def test_unknown_flower_is_ignored(client, catalog):
    assert len(names(client.get(reverse('products'), {'flower': '<script>'}))) == 4


@pytest.mark.parametrize(
    ('sort', 'first'),
    [('price_asc', 'Cheap Roses'), ('price_desc', 'Big Orchids'), ('nonsense', None)],
)
def test_sorting(client, catalog, sort, first):
    response = client.get(reverse('products'), {'sort': sort})
    if first:
        assert names(response)[0] == first
    else:
        assert response.context['sort'] == 'popular'


def test_category_title_and_chips_keep_filters(client, catalog):
    response = client.get(reverse('products'), {'category': 'wedding', 'price': 'over-2000'})
    html = response.content.decode()
    assert response.context['title'] == 'Wedding'
    assert '?category=roses&amp;price=over-2000' in html or 'price=over-2000&amp;category=roses' in html


def test_empty_results_message(client, catalog):
    html = client.get(reverse('products'), {'q': 'cactus'}).content.decode()
    assert 'No bouquets match' in html


def test_product_page_gallery_rating_and_recommendations(client, catalog, customer):
    product = catalog['mid_lily']
    Review.objects.create(product=product, user=customer, rating=2, comment='Meh')
    response = client.get(reverse('product_detail', args=[product.pk]))
    html = response.content.decode()
    assert response.context['rating_avg'] == 2
    assert 'aria-label="2 out of 5 stars"' in html  # each review shows its own rating
    assert response.context['gallery'] == [product.get_image]
    assert catalog['cheap_rose'] in response.context['recommendations']
    assert 'data-pin-auto' in html
    assert 'id="buy-bar"' in html


def test_sold_out_product_page(client, catalog):
    product = catalog['sold_out']
    product.stock_quantity = 0
    product.save()
    html = client.get(reverse('product_detail', args=[product.pk])).content.decode()
    assert 'Sold out' in html
    assert 'id="add-main"' not in html
    assert 'id="buy-bar"' not in html


def test_quantity_is_capped_at_ten(client, catalog):
    product = catalog['cheap_rose']
    product.stock_quantity = 50
    product.save()
    assert client.get(reverse('product_detail', args=[product.pk])).context['max_qty'] == 10
