"""Browsing products, reviews, search, wishlist and the custom bouquet builder."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from bloomapp.forms import CustomBouquetForm, first_error
from bloomapp.models import (
    FLOWER_CHOICES,
    WRAPPING_CHOICES,
    CartItem,
    Category,
    CustomBouquet,
    Product,
    Review,
    Wishlist,
)
from bloomapp.services import pricing
from bloomapp.utils import back_url, parse_float, parse_int

SORTS = {
    'popular': ('Most popular', ('-order_count', '-is_featured', '-created_at')),
    'newest': ('Newest', ('-created_at',)),
    'price_asc': ('Price: low to high', ('price',)),
    'price_desc': ('Price: high to low', ('-price',)),
}
PRICE_BANDS = {
    'under-1000': ('Under ₹1,000', None, 999.99),
    '1000-2000': ('₹1,000 – ₹2,000', 1000, 2000),
    'over-2000': ('Over ₹2,000', 2000.01, None),
}


def with_ratings(products):
    """Add order and review counts so cards can show ratings and sort by popularity."""
    return products.annotate(
        order_count=Count('orderitem', distinct=True),
        review_count=Count('reviews', distinct=True),
        rating_avg=Avg('reviews__rating'),
    )


def _wishlist_ids(user):
    if not user.is_authenticated:
        return set()
    return set(Wishlist.objects.filter(user=user).values_list('product_id', flat=True))


def products_list(request):
    params = request.GET
    base = Product.objects.filter(status='available').select_related('category')

    category = Category.objects.filter(slug=params.get('category', ''), status='available').first()
    q = params.get('q', '').strip()[:100]
    price = params.get('price', '')
    flowers = [f for f in params.getlist('flower') if f in dict(FLOWER_CHOICES)]
    sort = params.get('sort') if params.get('sort') in SORTS else 'popular'

    if category:
        base = base.filter(Q(category=category) | Q(extra_categories=category)).distinct()
    if q:
        base = base.filter(Q(name__icontains=q) | Q(description__icontains=q) | Q(flowers__icontains=q))
    # Older links (home page "under ₹X") still work.
    min_price = parse_float(params.get('min_price'), None, min_value=0)
    max_price = parse_float(params.get('max_price'), None, min_value=0)
    if price in PRICE_BANDS:
        _, min_price, max_price = PRICE_BANDS[price]
    if min_price is not None:
        base = base.filter(price__gte=min_price)
    if max_price is not None:
        base = base.filter(price__lte=max_price)

    # Count each flower among the products the other filters leave, so the numbers are honest.
    flower_names = list(base.values_list('flowers', flat=True))
    flower_options = [
        {
            'key': key,
            'label': label,
            # Same rule as the filter below (substring match), so the count always equals the results.
            'count': sum(key in (names or '').lower() for names in flower_names),
            'checked': key in flowers,
        }
        for key, label in FLOWER_CHOICES
    ]

    products = base
    if flowers:
        match = Q()
        for key in flowers:
            match |= Q(flowers__icontains=key)
        products = products.filter(match)
    products = with_ratings(products).order_by(*SORTS[sort][1])

    if category:
        title = category.name
    elif q:
        title = f'Results for “{q}”'
    else:
        title = 'All bouquets'

    return render(
        request,
        'bloomapp/products/list.html',
        {
            'products': products,
            'title': title,
            'categories': Category.objects.filter(status='available').order_by('name'),
            'selected_category': category,
            'search_q': q,
            'price': price if price in PRICE_BANDS else '',
            'price_bands': [(key, label) for key, (label, _, _) in PRICE_BANDS.items()],
            'flower_options': flower_options,
            'sort': sort,
            'sort_options': [(key, label) for key, (label, _) in SORTS.items()],
            'active_filter_count': (1 if price in PRICE_BANDS else 0) + len(flowers),
            'wishlist_ids': _wishlist_ids(request.user),
        },
    )


def product_detail(request, pk):
    product = get_object_or_404(Product.objects.select_related('category'), pk=pk, status='available')
    reviews = list(product.reviews.select_related('user').order_by('-created_at'))
    gallery = [product.get_image] + [img.url for img in (product.image_2, product.image_3) if img]
    recommendations = with_ratings(
        Product.objects.filter(Q(category=product.category) | Q(extra_categories=product.category), status='available')
        .exclude(pk=pk)
        .select_related('category')
        .distinct()
    ).order_by('-order_count', '-is_featured')[:4]
    wishlist_ids = _wishlist_ids(request.user)
    rating_avg = round(sum(r.rating for r in reviews) / len(reviews), 1) if reviews else None
    return render(
        request,
        'bloomapp/products/detail.html',
        {
            'product': product,
            'gallery': gallery,
            'reviews': reviews,
            'rating_avg': rating_avg,
            'recommendations': recommendations,
            'wishlist_ids': wishlist_ids,
            'in_wishlist': product.pk in wishlist_ids,
            'max_qty': min(product.stock_quantity, 10),
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
        messages.success(request, 'Thanks for your review.')
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


# Free-licensed demo photos (see photo_credits.json) shown on the bouquet builder.
BOUQUET_PHOTOS = {
    'rose': 'bloomapp/demo/products/romantic-red-rose-bouquet.jpg',
    'lily': 'bloomapp/demo/products/sympathy-white-lilies.jpg',
    'tulip': 'bloomapp/demo/products/rainbow-tulip-mix.jpg',
    'sunflower': 'bloomapp/demo/products/sunshine-sunflower-bunch.jpg',
    'orchid': 'bloomapp/demo/products/orchid-paradise.jpg',
}
WRAP_LOOKS = {
    'classic': {'desc': 'Crisp white paper, satin ribbon', 'swatch': '#F7F3EE'},
    'rustic': {'desc': 'Brown kraft paper and twine', 'swatch': '#C9A67A'},
    'luxury': {'desc': 'Wine satin with a gift box', 'swatch': '#7B2D3B'},
    'minimal': {'desc': 'Sage tissue, no plastic', 'swatch': '#A9BCA3'},
}


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
        messages.success(request, 'Custom bouquet added to your cart.')
        return redirect('cart')
    return render(
        request,
        'bloomapp/bouquet/custom.html',
        {
            'bouquet_pricing': pricing.bouquet_pricing_config(),
            'flower_options': [
                {'key': key, 'label': label, 'extra': pricing.FLOWER_SURCHARGES[key], 'image': BOUQUET_PHOTOS[key]}
                for key, label in FLOWER_CHOICES
            ],
            'wrap_options': [
                {'key': key, 'label': label, 'cost': pricing.WRAPPING_COSTS[key], **WRAP_LOOKS[key]}
                for key, label in WRAPPING_CHOICES
            ],
            'stem_presets': [6, 12, 18, 24, 36],
            'min_stems': pricing.BOUQUET_MIN_STEMS,
            'max_stems': pricing.BOUQUET_MAX_STEMS,
        },
    )


@login_required
def wishlist_view(request):
    products = with_ratings(
        Product.objects.filter(wishlisted_by__user=request.user).select_related('category')
    ).order_by('-wishlisted_by__added_at')
    products = list(products)
    return render(
        request,
        'bloomapp/wishlist/wishlist.html',
        {'products': products, 'wishlist_ids': {p.pk for p in products}},
    )


@login_required
@require_POST
def toggle_wishlist(request, pk):
    product = get_object_or_404(Product, pk=pk)
    obj, created = Wishlist.objects.get_or_create(user=request.user, product=product)
    if created:
        msg = f'"{product.name}" saved to your wishlist.'
    else:
        obj.delete()
        msg = f'"{product.name}" removed from wishlist.'
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'in_wishlist': created, 'message': msg})
    messages.success(request, msg)
    return redirect(back_url(request, 'products'))
