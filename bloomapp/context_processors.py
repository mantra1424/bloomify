from .models import CartItem, Category
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
        # Lazy queryset: only hits the database when a template loops over it.
        'nav_categories': Category.objects.filter(status='available').order_by('name'),
        'delivery_city_names': pricing.serviceable_city_names(),
        'free_delivery_above': pricing.FREE_DELIVERY_ABOVE,
    }
