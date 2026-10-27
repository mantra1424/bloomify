"""Shopping cart."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from bloomapp.models import CartItem, Product
from bloomapp.services.orders import release_expired_online_orders
from bloomapp.utils import back_url, parse_int

MAX_QTY_PER_ITEM = 100


def cart_items_for(user):
    return CartItem.objects.filter(user=user).select_related('product', 'custom_bouquet')


@login_required
def cart_view(request):
    items = cart_items_for(request.user)
    return render(
        request,
        'bloomapp/cart/cart.html',
        {
            'items': items,
            'subtotal': sum(item.subtotal for item in items),
        },
    )


@login_required
@require_POST
def add_to_cart(request, pk):
    release_expired_online_orders()  # may free up stock held by abandoned payments
    product = get_object_or_404(Product, pk=pk, status='available')
    qty = parse_int(request.POST.get('quantity'), 1, min_value=1, max_value=MAX_QTY_PER_ITEM)
    back = back_url(request, 'products')

    if product.stock_quantity <= 0:
        messages.error(request, f'❌ "{product.name}" is out of stock.')
        return redirect(back)

    item = CartItem.objects.filter(user=request.user, product=product).first()
    in_cart = item.quantity if item else 0
    qty = min(qty, product.stock_quantity - in_cart)
    if qty <= 0:
        messages.warning(request, f'⚠️ You already have the maximum available stock of "{product.name}" in your cart.')
        return redirect(back)

    if item:
        item.quantity += qty
        item.save(update_fields=['quantity'])
    else:
        CartItem.objects.create(user=request.user, product=product, quantity=qty)
    messages.success(request, f'"{product.name}" added to cart! 🛒')
    return redirect(back)


@login_required
@require_POST
def update_cart(request):
    item_id = parse_int(request.POST.get('item_id'), None)
    qty = parse_int(request.POST.get('quantity'), 1, max_value=MAX_QTY_PER_ITEM)
    item = cart_items_for(request.user).filter(id=item_id).first() if item_id else None
    if item:
        if item.product and qty > item.product.stock_quantity:
            qty = item.product.stock_quantity
            messages.warning(request, f'⚠️ Only {qty} of "{item.product.name}" in stock.')
        if qty <= 0:
            item.delete()
        else:
            item.quantity = qty
            item.save(update_fields=['quantity'])
    return redirect('cart')


@login_required
@require_POST
def remove_from_cart(request, item_id):
    CartItem.objects.filter(id=item_id, user=request.user).delete()
    messages.success(request, 'Item removed from cart.')
    return redirect('cart')
