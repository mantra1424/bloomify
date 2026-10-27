"""Browsing products, reviews, search, wishlist and the custom bouquet builder."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from bloomapp.forms import CustomBouquetForm, first_error
from bloomapp.models import CartItem, Category, CustomBouquet, Product, Review, Wishlist
from bloomapp.services import pricing
from bloomapp.utils import back_url, parse_float, parse_int

OCCASIONS = ['birthday', 'anniversary', 'love', 'wedding', 'graduation', 'sympathy']
SORTS = {
    'price_asc': ('price',),
    'price_desc': ('-price',),
    'newest': ('-created_at',),
}


def _wishlist_ids(user):
    if not user.is_authenticated:
        return set()
    return set(Wishlist.objects.filter(user=user).values_list('product_id', flat=True))


def products_list(request):
    products = Product.objects.filter(status='available').select_related('category')

    cat_slug = request.GET.get('category', '')
    min_price = parse_float(request.GET.get('min_price'), None, min_value=0)
    max_price = parse_float(request.GET.get('max_price'), None, min_value=0)
    q = request.GET.get('q', '').strip()
    occasion = request.GET.get('occasion', '')
    sort = request.GET.get('sort', 'newest')

    if cat_slug:
        products = products.filter(Q(category__slug=cat_slug) | Q(extra_categories__slug=cat_slug)).distinct()
    if min_price is not None:
        products = products.filter(price__gte=min_price)
    if max_price is not None:
        products = products.filter(price__lte=max_price)
    if q:
        products = products.filter(Q(name__icontains=q) | Q(description__icontains=q) | Q(flowers__icontains=q))
    if occasion:
        products = products.filter(occasion_tags__icontains=occasion)

    if sort == 'popular':
        products = products.annotate(ocount=Count('orderitem')).order_by('-ocount')
    else:
        products = products.order_by(*SORTS.get(sort, SORTS['newest']))

    return render(
        request,
        'bloomapp/products/list.html',
        {
            'products': products,
            'categories': Category.objects.filter(status='available'),
            'selected_cat': cat_slug,
            'min_price': request.GET.get('min_price', ''),
            'max_price': request.GET.get('max_price', ''),
            'search_q': q,
            'sort': sort,
            'occasion': occasion,
            'occasion_choices': OCCASIONS,
            'wishlist_ids': _wishlist_ids(request.user),
        },
    )


def product_detail(request, pk):
    product = get_object_or_404(Product.objects.select_related('category'), pk=pk, status='available')
    recommendations = (
        Product.objects.filter(Q(category=product.category) | Q(extra_categories=product.category), status='available')
        .exclude(pk=pk)
        .distinct()
        .annotate(ocount=Count('orderitem'))
        .order_by('-ocount')[:4]
    )
    return render(
        request,
        'bloomapp/products/detail.html',
        {
            'product': product,
            'reviews': product.reviews.select_related('user').order_by('-created_at'),
            'recommendations': recommendations,
            'star_range': range(1, 6),
            'avg_rating': product.avg_rating,
            'in_wishlist': product.pk in _wishlist_ids(request.user),
        },
    )


@login_required
@require_POST
def submit_review(request, pk):
    product = get_object_or_404(Product, pk=pk)
    rating = parse_int(request.POST.get('rating'), 5, min_value=1, max_value=5)
    comment = request.POST.get('comment', '').strip()[:2000]
    if comment:
        # One review per user per product; a second submission updates the first.
        Review.objects.update_or_create(
            product=product, user=request.user, defaults={'rating': rating, 'comment': comment}
        )
        messages.success(request, 'Review submitted! Thank you 🌸')
    return redirect('product_detail', pk=pk)


def search_autocomplete(request):
    q = request.GET.get('q', '').strip()
    if len(q) < 2:
        return JsonResponse({'results': []})
    products = (
        Product.objects.filter(status='available')
        .filter(Q(name__icontains=q) | Q(flowers__icontains=q) | Q(occasion_tags__icontains=q))
        .select_related('category')[:8]
    )
    return JsonResponse(
        {
            'results': [
                {
                    'id': p.pk,
                    'name': p.name,
                    'price': str(p.price),
                    'image': p.get_image,
                    'url': reverse('product_detail', args=[p.pk]),
                    'category': p.category.name,
                }
                for p in products
            ]
        }
    )


@login_required
def custom_bouquet_view(request):
    if request.method == 'POST':
        form = CustomBouquetForm(request.POST)
        if not form.is_valid():
            messages.error(request, first_error(form))
            return redirect('custom_bouquet')
        data = form.cleaned_data
        bouquet = CustomBouquet.objects.create(
            user=request.user,
            flowers=data['flowers'],
            flower_count=data['flower_count'],
            wrapping=data['wrapping'],
            message_card=data.get('message_card', '').strip(),
            price=form.price(),
        )
        CartItem.objects.create(user=request.user, custom_bouquet=bouquet, quantity=1)
        messages.success(request, 'Custom bouquet added to cart! 🌺')
        return redirect('cart')
    return render(request, 'bloomapp/bouquet/custom.html', {'bouquet_pricing': pricing.bouquet_pricing_config()})


@login_required
def wishlist_view(request):
    items = Wishlist.objects.filter(user=request.user).select_related('product', 'product__category')
    return render(request, 'bloomapp/wishlist/wishlist.html', {'items': items})


@login_required
@require_POST
def toggle_wishlist(request, pk):
    product = get_object_or_404(Product, pk=pk)
    obj, created = Wishlist.objects.get_or_create(user=request.user, product=product)
    if created:
        msg = f'"{product.name}" added to wishlist! ♥'
    else:
        obj.delete()
        msg = f'"{product.name}" removed from wishlist.'
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'in_wishlist': created, 'message': msg})
    messages.success(request, msg)
    return redirect(back_url(request, 'products'))
