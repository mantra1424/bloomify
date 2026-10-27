from .models import CartItem


def cart_count(request):
    """Number of items in the logged-in user's cart, for the navbar badge."""
    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated:
        return {'cart_count': 0}
    return {'cart_count': CartItem.objects.filter(user=user).count()}
