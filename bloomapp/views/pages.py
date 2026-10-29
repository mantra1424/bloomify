"""Home page, static pages, contact form, newsletter and health check."""

import json
from functools import cache
from pathlib import Path

from django.contrib import messages
from django.core.validators import validate_email
from django.db import connection
from django.db.models import Avg, Count
from django.forms import ValidationError
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from bloomapp.forms import ContactForm, first_error
from bloomapp.models import Category, NewsletterSubscriber, Product, Wishlist


def home(request):
    available = Product.objects.filter(status='available').select_related('category')

    # Each occasion tile shows a photo: its featured product's, else its newest product's.
    tile_image = {}
    for product in available.order_by('-is_featured', '-created_at'):
        tile_image.setdefault(product.category_id, product.get_image)
    occasions = [
        {'category': cat, 'image': tile_image.get(cat.id)}
        for cat in Category.objects.filter(status='available').order_by('name')
        if cat.id in tile_image
    ]

    # Bestsellers: most ordered, then featured, then newest.
    bestsellers = available.annotate(
        order_count=Count('orderitem', distinct=True),
        review_count=Count('reviews', distinct=True),
        rating_avg=Avg('reviews__rating'),
    ).order_by('-order_count', '-is_featured', '-created_at')[:4]

    return render(
        request,
        'bloomapp/index.html',
        {
            'occasions': occasions,
            'bestsellers': bestsellers,
            'wishlist_ids': _wishlist_ids(request.user),
            'hero_image': 'bloomapp/demo/products/pink-garden-delight.jpg',
        },
    )


def _wishlist_ids(user):
    if not user.is_authenticated:
        return set()
    return set(Wishlist.objects.filter(user=user).values_list('product_id', flat=True))


def contact_view(request):
    success = False
    if request.method == 'POST':
        form = ContactForm(request.POST)
        if form.is_valid():
            form.save()
            success = True
        else:
            messages.error(request, first_error(form))
    return render(request, 'bloomapp/contact.html', {'success': success})


def faq_view(request):
    return render(request, 'bloomapp/faq.html')


def returns_view(request):
    return render(request, 'bloomapp/returns.html')


@cache
def _photo_credits():
    path = Path(__file__).resolve().parent.parent / 'data' / 'photo_credits.json'
    return json.loads(path.read_text(encoding='utf-8'))


def photo_credits_view(request):
    """Attribution for the free-licensed demo product photos (required by CC BY licences)."""
    return render(request, 'bloomapp/photo_credits.html', {'credits': _photo_credits()})


@require_POST
def newsletter_subscribe(request):
    email = request.POST.get('email', '').strip().lower()
    try:
        validate_email(email)
    except ValidationError:
        return JsonResponse({'ok': False, 'message': 'Invalid email address.'}, status=400)
    _, created = NewsletterSubscriber.objects.get_or_create(email=email)
    if created:
        return JsonResponse({'ok': True, 'message': 'Subscribed! Thank you 🌸'})
    return JsonResponse({'ok': True, 'message': "You're already subscribed!"})


@require_GET
def healthz(request):
    """Used by Render/Docker to check the app and database are up."""
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
    except Exception:
        return JsonResponse({'status': 'error', 'database': 'unreachable'}, status=503)
    return JsonResponse({'status': 'ok'})
