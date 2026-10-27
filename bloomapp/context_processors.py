from .models import CartItem, User

def cart_count(request):
    count = 0
    user_id = request.session.get('user_id')
    if user_id:
        try:
            user = User.objects.get(id=user_id)
            count = CartItem.objects.filter(user=user).count()
        except User.DoesNotExist:
            pass
    return {'cart_count': count}
