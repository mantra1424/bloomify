"""Home page, static pages, contact form, newsletter and health check."""

import json
from functools import cache
from pathlib import Path

from django.contrib import messages
from django.core.validators import validate_email
from django.db import connection
from django.db.models import Count
from django.forms import ValidationError
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from bloomapp.forms import ContactForm, first_error
from bloomapp.models import Category, NewsletterSubscriber, Product


def home(request):
    available = Product.objects.filter(status='available').select_related('category')
    return render(
        request,
        'bloomapp/index.html',
        {
            'categories': Category.objects.filter(status='available'),
            'featured': available.filter(is_featured=True)[:8],
            # Trending = most ordered products.
            'trending': available.annotate(order_count=Count('orderitem')).order_by('-order_count')[:4],
        },
    )


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
