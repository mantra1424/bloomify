from django.conf import settings
from django.utils.functional import SimpleLazyObject

from .models import CartItem, Category
from .services import cache as catalog_cache
from .services import pricing


def cart_count(request):
    """Number of items in the logged-in user's cart, for the navbar badge."""
    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated:
        return {'cart_count': 0}
    return {'cart_count': CartItem.objects.filter(user=user).count()}


def site_nav(request):
    """Header/footer data: occasions for the menu and the delivery promise."""
    return {
        'brand': settings.SITE_BRAND,
        'pwa_enabled': settings.PWA_ENABLED,
        # Most pages show the menu, so it comes from the cache, and only when a template uses it.
        'nav_categories': SimpleLazyObject(lambda: catalog_cache.cached('nav_categories', _nav_categories)),
        'delivery_city_names': pricing.serviceable_city_names(),
        'free_delivery_above': pricing.FREE_DELIVERY_ABOVE,
    }


def _nav_categories():
    return list(Category.objects.filter(status='available').order_by('name'))
