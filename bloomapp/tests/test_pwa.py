"""Installable app: manifest, service worker, offline page and Android asset links."""

import pytest
from django.contrib.staticfiles import finders
from django.urls import reverse

pytestmark = pytest.mark.django_db


def test_manifest_describes_an_installable_app(client, settings):
    settings.SITE_BRAND = 'Petal & Stem'
    res = client.get('/manifest.webmanifest')
    assert res['Content-Type'] == 'application/manifest+json'
    data = res.json()
    assert data['short_name'] == 'Petal & Stem'
    assert data['display'] == 'standalone' and data['start_url'].startswith('/')
    sizes = {(icon['sizes'], icon['purpose']) for icon in data['icons']}
    assert {('192x192', 'any'), ('512x512', 'any'), ('512x512', 'maskable')} <= sizes
    for icon in data['icons']:
        assert finders.find(icon['src'].removeprefix('/static/')), icon['src']


def test_pages_link_the_manifest_and_register_the_worker(client, settings):
    settings.PWA_ENABLED = True
    html = client.get(reverse('home')).content.decode()
    assert 'rel="manifest" href="/manifest.webmanifest"' in html
    assert 'data-sw="/sw.js"' in html


def test_worker_is_not_registered_when_disabled(client, settings):
    settings.PWA_ENABLED = False
    assert 'data-sw=' not in client.get(reverse('home')).content.decode()


def test_service_worker_is_served_from_the_root(client):
    res = client.get('/sw.js')
    assert res['Content-Type'] == 'application/javascript'
    assert res['Service-Worker-Allowed'] == '/'
    body = res.content.decode()
    assert "const OFFLINE_URL = '/offline/';" in body
    assert '/static/css/main.css' in body and '&#x27;' not in body


def test_offline_page_works_without_the_database(client, django_assert_num_queries):
    with django_assert_num_queries(0):
        res = client.get('/offline/')
    assert res.status_code == 200 and b"You're offline" in res.content


def test_assetlinks_lists_the_android_app_once_configured(client, settings):
    settings.ANDROID_APP_PACKAGE = 'com.petalandstem.app'
    settings.ANDROID_APP_SHA256_FINGERPRINTS = []
    assert client.get('/.well-known/assetlinks.json').json() == []

    settings.ANDROID_APP_SHA256_FINGERPRINTS = ['AA:BB']
    target = client.get('/.well-known/assetlinks.json').json()[0]['target']
    assert target == {
        'namespace': 'android_app',
        'package_name': 'com.petalandstem.app',
        'sha256_cert_fingerprints': ['AA:BB'],
    }
