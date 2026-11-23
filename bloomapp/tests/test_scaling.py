"""Caching (with stampede protection), background tasks and request monitoring."""

import io
import logging
import time

import pytest
from django.core.cache import cache
from django.core.management import call_command
from django.tasks import TaskResultStatus
from django.urls import reverse

from bloomapp.models import Category, Product
from bloomapp.services import cache as catalog_cache

pytestmark = pytest.mark.django_db


@pytest.fixture
def caching(settings):
    settings.CATALOG_CACHE_SECONDS = 300
    cache.clear()
    yield
    cache.clear()


class Builder:
    def __init__(self, value='fresh'):
        self.value, self.calls = value, 0

    def __call__(self):
        self.calls += 1
        return self.value


# ── Cache-aside ────────────────────────────────────────────────────────────
def test_value_is_built_once_then_served_from_cache(caching):
    build = Builder()
    assert catalog_cache.cached('x', build) == 'fresh'
    assert catalog_cache.cached('x', build) == 'fresh'
    assert build.calls == 1


def test_editing_the_catalog_clears_cached_data(caching, category):
    build = Builder()
    catalog_cache.cached('x', build)
    Product.objects.create(name='New', category=category, original_price=100, price=100)
    catalog_cache.cached('x', build)
    assert build.calls == 2


def test_caching_can_be_turned_off(settings):
    settings.CATALOG_CACHE_SECONDS = 0
    build = Builder()
    catalog_cache.cached('x', build)
    catalog_cache.cached('x', build)
    assert build.calls == 2


# ── Stampede protection ────────────────────────────────────────────────────
def _make_stale(name):
    key = f'catalog:{catalog_cache.catalog_version()}:{name}'
    entry = cache.get(key)
    entry['fresh_until'] = time.time() - 1
    cache.set(key, entry)
    return key


def test_stale_copy_is_served_while_another_request_rebuilds(caching):
    catalog_cache.cached('x', Builder('old'))
    key = _make_stale('x')
    cache.add(f'{key}:lock', 1)  # another request is rebuilding right now
    build = Builder('new')
    assert catalog_cache.cached('x', build) == 'old'
    assert build.calls == 0


def test_stale_copy_is_rebuilt_by_one_request(caching):
    catalog_cache.cached('x', Builder('old'))
    _make_stale('x')
    assert catalog_cache.cached('x', Builder('new')) == 'new'
    assert catalog_cache.cached('x', Builder('newer')) == 'new'  # fresh again


def test_cold_cache_waits_for_the_rebuild_in_progress(caching, monkeypatch):
    key = f'catalog:{catalog_cache.catalog_version()}:x'
    cache.add(f'{key}:lock', 1)
    # The other request finishes its rebuild while this one waits.
    monkeypatch.setattr(time, 'sleep', lambda s: cache.set(key, {'value': 'theirs', 'fresh_until': time.time() + 60}))
    build = Builder('mine')
    assert catalog_cache.cached('x', build) == 'theirs'
    assert build.calls == 0


def test_expiry_times_are_spread_out(caching):
    for i in range(20):
        catalog_cache.cached(f'k{i}', Builder())
    version = catalog_cache.catalog_version()
    expiries = {round(cache.get(f'catalog:{version}:k{i}')['fresh_until'], 3) for i in range(20)}
    assert len(expiries) > 1


def test_lock_is_released_when_the_build_fails(caching):
    def broken():
        raise RuntimeError('db down')

    with pytest.raises(RuntimeError):
        catalog_cache.cached('x', broken)
    assert catalog_cache.cached('x', Builder('ok')) == 'ok'


# ── Pages ──────────────────────────────────────────────────────────────────
def test_home_page_reads_the_catalog_from_cache(caching, client, product, django_assert_max_num_queries):
    client.get(reverse('home'))  # fills the cache
    with django_assert_max_num_queries(1):  # only the session/user lookup is left, if any
        html = client.get(reverse('home')).content.decode()
    assert product.name in html


def test_new_product_shows_on_the_home_page_straight_away(caching, client, product):
    client.get(reverse('home'))
    product.name = 'Renamed Roses'
    product.save()
    assert 'Renamed Roses' in client.get(reverse('home')).content.decode()


def test_sold_out_badge_updates_when_stock_comes_back(caching, client, customer, product):
    from bloomapp.services.orders import release_order
    from bloomapp.tests.test_polish import make_order

    order = make_order(customer)
    client.get(reverse('home'))
    version = catalog_cache.catalog_version()
    release_order(order)
    assert catalog_cache.catalog_version() != version


def test_warm_cache_fills_the_cache(caching, product):
    call_command('warm_cache', stdout=io.StringIO())
    version = catalog_cache.catalog_version()
    assert cache.get(f'catalog:{version}:home') and cache.get(f'catalog:{version}:nav_categories')


def test_menu_is_not_loaded_on_pages_that_do_not_show_it(caching, client, django_assert_num_queries):
    Category.objects.create(name='Roses', slug='roses-x')
    with django_assert_num_queries(0):
        client.get('/offline/')


# ── Background tasks ───────────────────────────────────────────────────────
def test_order_confirmation_task_sends_the_email(customer, mailoutbox):
    from bloomapp.tasks import send_order_confirmation
    from bloomapp.tests.test_polish import make_order

    order = make_order(customer)
    result = send_order_confirmation.enqueue(order.id)
    assert result.status == TaskResultStatus.SUCCESSFUL and result.return_value == 'sent'
    assert mailoutbox[0].to == [order.email]


def test_order_confirmation_task_skips_deleted_orders(mailoutbox):
    from bloomapp.tasks import send_order_confirmation

    assert send_order_confirmation.enqueue(999999).return_value == 'missing'
    assert not mailoutbox


# ── Monitoring ─────────────────────────────────────────────────────────────
def test_every_response_has_a_request_id_and_timing(client):
    res = client.get(reverse('faqs'))
    assert len(res['X-Request-ID']) == 32
    assert res['Server-Timing'].startswith('app;dur=')


def test_platform_request_id_is_reused_but_unsafe_ones_are_replaced(client):
    assert client.get(reverse('faqs'), HTTP_X_REQUEST_ID='abc-12345678')['X-Request-ID'] == 'abc-12345678'
    assert client.get(reverse('faqs'), HTTP_X_REQUEST_ID='<script>')['X-Request-ID'] != '<script>'


def test_slow_requests_are_logged(client, settings, caplog):
    settings.SLOW_REQUEST_MS = 0
    with caplog.at_level(logging.WARNING, logger='bloomapp.requests'):
        res = client.get(reverse('faqs'))
    assert 'Slow request GET /faqs/ status=200' in caplog.text
    assert res['X-Request-ID'] in caplog.text


# ── When the cache itself fails ────────────────────────────────────────────
@pytest.fixture
def cache_down(caching, monkeypatch):
    def broken(*args, **kwargs):
        raise ConnectionError('redis down')

    for method in ('get', 'set', 'add', 'delete', 'incr'):
        monkeypatch.setattr(cache, method, broken)


def test_pages_still_work_when_the_cache_is_down(cache_down, client, product, caplog):
    with caplog.at_level(logging.WARNING, logger='bloomapp.services.cache'):
        html = client.get(reverse('home')).content.decode()
    assert product.name in html
    assert 'Cache unreachable (ConnectionError)' in caplog.text


def test_editing_products_still_works_when_the_cache_is_down(cache_down, category):
    Product.objects.create(name='Saved anyway', category=category, original_price=100, price=100)
    assert Product.objects.filter(name='Saved anyway').exists()


def test_health_check_reports_the_cache(caching, client):
    assert client.get(reverse('healthz')).json() == {'status': 'ok', 'cache': {'backend': 'memory', 'ok': True}}


def test_health_check_stays_up_when_the_cache_is_down(cache_down, client):
    res = client.get(reverse('healthz'))
    assert res.status_code == 200 and res.json()['cache'] == {'backend': 'memory', 'ok': False}
