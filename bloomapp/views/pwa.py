"""
Installable app support: web app manifest, service worker, offline page and the
Digital Asset Links file that lets the Android app open the site full-screen.
"""

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.templatetags.static import static
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_GET

THEME_COLOR = '#7B2D3B'
BACKGROUND_COLOR = '#FBF7F2'


@require_GET
@cache_control(max_age=3600, public=True)
def manifest(request):
    brand = settings.SITE_BRAND
    data = {
        'id': '/',
        'name': f'{brand} – Flower Delivery',
        'short_name': brand,
        'description': 'Hand-tied bouquets with same-day and midnight delivery in Gujarat.',
        'start_url': '/?source=app',
        'scope': '/',
        'display': 'standalone',
        'orientation': 'portrait',
        'theme_color': THEME_COLOR,
        'background_color': BACKGROUND_COLOR,
        'lang': 'en-IN',
        'categories': ['shopping', 'lifestyle'],
        'icons': [
            _icon('icon-192.png', '192x192', 'any'),
            _icon('icon-512.png', '512x512', 'any'),
            _icon('icon-maskable-512.png', '512x512', 'maskable'),
        ],
        'shortcuts': [
            {'name': 'Shop bouquets', 'url': '/products/?source=app'},
            {'name': 'Design your own', 'url': '/custom-bouquet/?source=app'},
            {'name': 'My orders', 'url': '/dashboard/?source=app'},
        ],
    }
    return JsonResponse(data, content_type='application/manifest+json', json_dumps_params={'ensure_ascii': False})


def _icon(name, sizes, purpose):
    return {'src': static(f'bloomapp/img/{name}'), 'sizes': sizes, 'type': 'image/png', 'purpose': purpose}


@require_GET
@cache_control(max_age=0, no_cache=True)
def service_worker(request):
    # Served from the site root (not /static/) so it can control every page.
    precache = [static(path) for path in ('css/main.css', 'js/main.js', 'bloomapp/img/logo-mark.svg')]
    response = render(
        request,
        'bloomapp/pwa/sw.js',
        {'offline_url': '/offline/', 'precache': precache},
        content_type='application/javascript',
    )
    response['Service-Worker-Allowed'] = '/'
    return response


@require_GET
def offline(request):
    return render(request, 'bloomapp/pwa/offline.html')


@require_GET
@cache_control(max_age=3600, public=True)
def assetlinks(request):
    """Proves to Android that the Petal & Stem app and this website belong together."""
    package = settings.ANDROID_APP_PACKAGE
    fingerprints = settings.ANDROID_APP_SHA256_FINGERPRINTS
    if not (package and fingerprints):
        return JsonResponse([], safe=False)
    return JsonResponse(
        [
            {
                'relation': ['delegate_permission/common.handle_all_urls'],
                'target': {
                    'namespace': 'android_app',
                    'package_name': package,
                    'sha256_cert_fingerprints': fingerprints,
                },
            }
        ],
        safe=False,
    )
