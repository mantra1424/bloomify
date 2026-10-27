from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.hashers import make_password, check_password
from django.utils import timezone
from django.db import transaction
from django.db.models import Sum, Count, Avg, Q, F
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.conf import settings
from datetime import datetime, date, timedelta
import json, razorpay, csv, re
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.http import HttpResponse

from .models import (
    User, SavedAddress, Category, Product, Review,
    DeliveryZone, DeliverySlot, Coupon, CustomBouquet,
    CartItem, Order, OrderItem, Payment, ContactMessage,
    Wishlist, NewsletterSubscriber, FLOWER_CHOICES, PAYMENT_MODE
)


# ──────────────────────────────────────────────────────────────────────────────
# INPUT HELPERS
# ──────────────────────────────────────────────────────────────────────────────

def _parse_int(value, default, min_value=None, max_value=None):
    """Turn form input into an int without crashing; clamp it to a range."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    if min_value is not None:
        n = max(min_value, n)
    if max_value is not None:
        n = min(max_value, n)
    return n


def _parse_float(value, default, min_value=None, max_value=None):
    try:
        n = float(value)
    except (TypeError, ValueError):
        return default
    if n != n:  # NaN
        return default
    if min_value is not None:
        n = max(min_value, n)
    if max_value is not None:
        n = min(max_value, n)
    return n


class _OutOfStock(Exception):
    def __init__(self, product):
        self.product = product


# ──────────────────────────────────────────────────────────────────────────────
# ORDER RELEASE (cancellation + abandoned online payments)
# ──────────────────────────────────────────────────────────────────────────────

ONLINE_PAYMENT_MODES = ('online', 'upi', 'card')


def _release_order(order, payment_status=None):
    """Cancel an order and give back its stock, coupon use and delivery slot."""
    with transaction.atomic():
        # Re-read and lock so two requests can't release the same order twice.
        order = Order.objects.select_for_update().get(pk=order.pk)
        if order.status == 'cancelled':
            return False
        for item in order.items.all():
            if item.product_id:
                Product.objects.filter(pk=item.product_id).update(
                    stock_quantity=F('stock_quantity') + item.quantity)
        if order.coupon_id:
            Coupon.objects.filter(pk=order.coupon_id, used_count__gt=0).update(
                used_count=F('used_count') - 1)
        if order.delivery_slot_id:
            DeliverySlot.objects.filter(pk=order.delivery_slot_id, booked_count__gt=0).update(
                booked_count=F('booked_count') - 1)
        order.status = 'cancelled'
        order.save(update_fields=['status', 'updated_at'])
        if payment_status:
            Payment.objects.filter(order=order).update(status=payment_status)
    return True


def release_expired_online_orders():
    """Cancel online orders whose payment never finished, so their stock comes back."""
    timeout = getattr(settings, 'PENDING_PAYMENT_TIMEOUT_MINUTES', 30)
    cutoff = timezone.now() - timedelta(minutes=timeout)
    expired = Order.objects.filter(
        status='placed',
        payment_mode__in=ONLINE_PAYMENT_MODES,
        payment__status='pending',
        created_at__lt=cutoff,
    )
    released = 0
    for order in expired:
        if _release_order(order, payment_status='expired'):
            released += 1
    return released

# ──────────────────────────────────────────────────────────────────────────────
# EMAIL HELPER
# ──────────────────────────────────────────────────────────────────────────────
def send_order_confirmation_email(order, items):
    """Send a beautifully formatted order confirmation email."""
    try:
        subject = f'🌸 Order #{order.id} Confirmed – Bloomify'
        item_rows = ''.join([
            f'<tr style="border-bottom:1px solid #f5e6eb;">'
            f'<td style="padding:10px 8px;font-size:14px;color:#333;">'
            f'{item.product.name if item.product else "Custom Bouquet"}</td>'
            f'<td style="padding:10px 8px;text-align:center;font-size:14px;color:#555;">×{item.quantity}</td>'
            f'<td style="padding:10px 8px;text-align:right;font-size:14px;font-weight:600;color:#c2185b;">₹{item.line_total}</td>'
            f'</tr>'
            for item in items
        ])
        discount_row = (
            f'<tr><td colspan="2" style="padding:6px 8px;font-size:13px;color:#16a34a;">Discount ({order.coupon.code})</td>'
            f'<td style="padding:6px 8px;text-align:right;font-size:13px;color:#16a34a;font-weight:600;">-₹{order.discount_amount}</td></tr>'
            if order.discount_amount > 0 else ''
        )
        html_message = f'''
        <!DOCTYPE html>
        <html>
        <body style="margin:0;padding:0;background:#fdf4f7;font-family:Inter,sans-serif;">
          <div style="max-width:560px;margin:32px auto;background:white;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(194,24,91,0.10);">
            <!-- Header -->
            <div style="background:linear-gradient(135deg,#c2185b,#e91e8c);padding:36px 32px;text-align:center;">
              <div style="font-size:42px;margin-bottom:8px;">🌸</div>
              <h1 style="color:white;margin:0;font-size:22px;font-weight:700;">Order Confirmed!</h1>
              <p style="color:rgba(255,255,255,0.85);margin:8px 0 0;font-size:14px;">Thank you for choosing Bloomify</p>
            </div>
            <!-- Body -->
            <div style="padding:28px 32px;">
              <p style="font-size:15px;color:#333;margin:0 0 4px;">Hi <strong>{order.full_name}</strong>,</p>
              <p style="font-size:14px;color:#666;margin:0 0 24px;">Your order <strong style="color:#c2185b;">#{order.id}</strong> has been placed successfully and is being prepared with love! 💐</p>

              <!-- Items Table -->
              <table style="width:100%;border-collapse:collapse;margin-bottom:16px;">
                <thead>
                  <tr style="background:#fdf4f7;">
                    <th style="padding:10px 8px;text-align:left;font-size:12px;color:#999;text-transform:uppercase;letter-spacing:1px;">Item</th>
                    <th style="padding:10px 8px;text-align:center;font-size:12px;color:#999;text-transform:uppercase;letter-spacing:1px;">Qty</th>
                    <th style="padding:10px 8px;text-align:right;font-size:12px;color:#999;text-transform:uppercase;letter-spacing:1px;">Price</th>
                  </tr>
                </thead>
                <tbody>
                  {item_rows}
                  <tr style="background:#fdf4f7;">
                    <td colspan="2" style="padding:8px;font-size:13px;color:#555;">Delivery</td>
                    <td style="padding:8px;text-align:right;font-size:13px;font-weight:600;color:#555;">{'FREE 🎉' if order.delivery_charge == 0 else f'₹{{order.delivery_charge}}'}</td>
                  </tr>
                  {discount_row}
                </tbody>
                <tfoot>
                  <tr style="border-top:2px solid #fce4ec;">
                    <td colspan="2" style="padding:12px 8px;font-size:16px;font-weight:700;color:#111;">Total Paid</td>
                    <td style="padding:12px 8px;text-align:right;font-size:18px;font-weight:800;color:#c2185b;">₹{order.total_amount}</td>
                  </tr>
                </tfoot>
              </table>

              <!-- Delivery Info -->
              <div style="background:#fdf4f7;border-radius:12px;padding:16px 20px;margin-bottom:20px;">
                <p style="margin:0 0 6px;font-size:13px;font-weight:700;color:#c2185b;text-transform:uppercase;letter-spacing:1px;">Delivery Details</p>
                <p style="margin:0;font-size:14px;color:#444;">{order.full_name} · {order.phone}</p>
                <p style="margin:4px 0 0;font-size:13px;color:#666;">{order.address}, {order.city} – {order.pincode}</p>
                <p style="margin:8px 0 0;font-size:13px;color:#888;">Payment: <strong style="color:#333;">{order.payment_mode.upper()}</strong></p>
              </div>

              <p style="font-size:13px;color:#888;margin:0;">We'll notify you when your order is out for delivery. 🚚<br/>For support, reply to this email or WhatsApp us at <strong>+91 94289 74532</strong>.</p>
            </div>
            <!-- Footer -->
            <div style="background:#fdf4f7;padding:16px 32px;text-align:center;border-top:1px solid #fce4ec;">
              <p style="margin:0;font-size:12px;color:#aaa;">© 2025 Bloomify · Made with 🌸 for flower lovers</p>
            </div>
          </div>
        </body>
        </html>
        '''
        send_mail(
            subject=subject,
            message=f'Order #{order.id} confirmed! Total: ₹{order.total_amount}. We will deliver to {order.city} soon.',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[order.email],
            html_message=html_message,
            fail_silently=True,   # never crash the order flow due to email
        )
    except Exception:
        pass  # email is best-effort; order is already saved


# ──────────────────────────────────────────────────────────────────────────────
# HELPERS / DECORATORS
# ──────────────────────────────────────────────────────────────────────────────

def get_current_user(request):
    uid = request.session.get('user_id')
    if uid:
        try:
            return User.objects.get(id=uid)
        except User.DoesNotExist:
            pass
    return None

def login_required_custom(view_fn):
    def wrapper(request, *args, **kwargs):
        if not request.session.get('user_id'):
            messages.error(request, 'Please log in to continue.')
            return redirect('login')
        return view_fn(request, *args, **kwargs)
    wrapper.__name__ = view_fn.__name__
    return wrapper

def contact_view(request):
    success = False
    if request.method == 'POST':
        ContactMessage.objects.create(
            name    = request.POST.get('name','').strip(),
            email   = request.POST.get('email','').strip(),
            phone   = request.POST.get('phone','').strip(),
            subject = request.POST.get('subject','Other'),
            message = request.POST.get('message','').strip(),
        )
        success = True
    return render(request, 'bloomapp/contact.html', {'success': success})


def faq_view(request):
    return render(request, 'bloomapp/faq.html')


def returns_view(request):
    return render(request, 'bloomapp/returns.html')


# ── Delivery Charge Calculation ──────────────────────────────────────────────
CITY_CHARGES  = {'anand':20,'vadodara':30,'ahmedabad':40,'surat':50,'bharuch':25,'vapi':60}
TIME_CHARGES  = {'normal':0,'sameday':50,'midnight':120}
ALLOWED_CITIES = list(CITY_CHARGES.keys())

def _calc_delivery(city: str, distance_km: float, delivery_type: str, subtotal: float) -> dict:
    city_key  = city.strip().lower()
    city_c    = CITY_CHARGES.get(city_key, 0)
    km        = _parse_float(distance_km, 3.0, min_value=0, max_value=500)
    dist_c    = 30 if km <= 5 else (60 if km <= 10 else 100)
    time_c    = TIME_CHARGES.get(delivery_type, 0)
    gross     = city_c + dist_c + time_c
    disc      = 0
    is_free   = subtotal >= 1000
    if is_free:
        disc, gross = gross, 0
    elif subtotal >= 500:
        disc  = min(30, gross)
        gross = max(0, gross - disc)
    return {'city_charge':city_c,'distance_charge':dist_c,'time_charge':time_c,
            'discount':disc,'delivery_charge':gross,'is_free':is_free}


@require_POST
def calculate_delivery_api(request):
    try:
        data          = json.loads(request.body)
        city          = str(data.get('city','')).strip()
        distance_km   = _parse_float(data.get('distance_km', 3), 3.0, min_value=0, max_value=500)
        delivery_type = str(data.get('delivery_type','normal'))
        subtotal      = _parse_float(data.get('subtotal', 0), 0.0, min_value=0)
    except (ValueError, KeyError, AttributeError, TypeError):
        return JsonResponse({'error':'Invalid input'}, status=400)
    if city.lower() not in ALLOWED_CITIES:
        return JsonResponse({'error':'City not serviceable'}, status=422)
    result = _calc_delivery(city, distance_km, delivery_type, subtotal)
    return JsonResponse(result)


def admin_required(view_fn):
    def wrapper(request, *args, **kwargs):
        uid = request.session.get('admin_id')
        if not uid:
            return redirect('admin_login')
        try:
            user = User.objects.get(id=uid)
            if not user.is_staff_member():
                return redirect('admin_login')
            request.admin_user = user
        except User.DoesNotExist:
            return redirect('admin_login')
        return view_fn(request, *args, **kwargs)
    wrapper.__name__ = view_fn.__name__
    return wrapper

def superadmin_required(view_fn):
    def wrapper(request, *args, **kwargs):
        uid = request.session.get('admin_id')
        if not uid:
            return redirect('admin_login')
        try:
            user = User.objects.get(id=uid)
            if not user.is_admin():
                messages.error(request, 'Admin access required.')
                return redirect('admin_dashboard')
            request.admin_user = user
        except User.DoesNotExist:
            return redirect('admin_login')
        return view_fn(request, *args, **kwargs)
    wrapper.__name__ = view_fn.__name__
    return wrapper


# ──────────────────────────────────────────────────────────────────────────────
# HOME
# ──────────────────────────────────────────────────────────────────────────────

def home(request):
    user = get_current_user(request)
    categories = Category.objects.filter(status='available')
    featured = Product.objects.filter(is_featured=True, status='available')[:8]
    # Smart recommendations: top-selling by order count
    trending = (
        Product.objects
        .filter(status='available')
        .annotate(order_count=Count('orderitem'))
        .order_by('-order_count')[:4]
    )
    return render(request, 'bloomapp/index.html', {
        'user': user,
        'categories': categories,
        'featured': featured,
        'trending': trending,
    })


# ──────────────────────────────────────────────────────────────────────────────
# AUTH
# ──────────────────────────────────────────────────────────────────────────────

def signup_view(request):
    if request.method == 'POST':
        full_name = request.POST.get('full_name', '').strip()
        email = request.POST.get('email', '').strip().lower()
        phone = request.POST.get('phone', '').strip()
        password = request.POST.get('password', '')
        confirm  = request.POST.get('confirm_password', '')

        if not all([full_name, email, password]):
            messages.error(request, 'All fields are required.')
            return render(request, 'bloomapp/auth/signup.html')
        if password != confirm:
            messages.error(request, 'Passwords do not match.')
            return render(request, 'bloomapp/auth/signup.html')
        if User.objects.filter(email=email).exists():
            messages.error(request, 'Email already registered. Please login.')
            return render(request, 'bloomapp/auth/signup.html')

        user = User.objects.create(
            full_name=full_name,
            email=email,
            phone=phone,
            password=make_password(password),
            role='user',
        )
        request.session['user_id'] = user.id
        request.session['user_name'] = user.full_name
        messages.success(request, f'Welcome to Bloomify, {user.full_name}! 🌸')
        return redirect('home')

    return render(request, 'bloomapp/auth/signup.html')


def login_view(request):
    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        password = request.POST.get('password', '')

        try:
            user = User.objects.get(email=email)
            if check_password(password, user.password):
                request.session['user_id'] = user.id
                request.session['user_name'] = user.full_name
                messages.success(request, f'Welcome back, {user.full_name}! 🌸')
                next_url = request.GET.get('next', 'home')
                return redirect(next_url)
            else:
                messages.error(request, 'Invalid password.')
        except User.DoesNotExist:
            messages.error(request, 'No account found with this email.')

    return render(request, 'bloomapp/auth/login.html')


def logout_view(request):
    request.session.pop('user_id', None)
    request.session.pop('user_name', None)
    messages.success(request, 'Logged out successfully.')
    return redirect('home')


# ──────────────────────────────────────────────────────────────────────────────
# PRODUCTS
# ──────────────────────────────────────────────────────────────────────────────

def products_list(request):
    products = Product.objects.filter(status='available').select_related('category')
    categories = Category.objects.filter(status='available')

    # Filters
    cat_slug = request.GET.get('category', '')
    min_price = request.GET.get('min_price', '')
    max_price = request.GET.get('max_price', '')
    q = request.GET.get('q', '')
    occasion = request.GET.get('occasion', '')
    sort = request.GET.get('sort', 'newest')

    if cat_slug:
        products = products.filter(
            Q(category__slug=cat_slug) | Q(extra_categories__slug=cat_slug)
        ).distinct()
    if min_price:
        products = products.filter(price__gte=min_price)
    if max_price:
        products = products.filter(price__lte=max_price)
    if q:
        products = products.filter(
            Q(name__icontains=q) | Q(description__icontains=q) | Q(flowers__icontains=q)
        )
    if occasion:
        products = products.filter(occasion_tags__icontains=occasion)

    if sort == 'price_asc':
        products = products.order_by('price')
    elif sort == 'price_desc':
        products = products.order_by('-price')
    elif sort == 'popular':
        products = products.annotate(ocount=Count('orderitem')).order_by('-ocount')
    else:
        products = products.order_by('-created_at')

    user = get_current_user(request)
    wishlist_ids = set()
    if user:
        wishlist_ids = set(Wishlist.objects.filter(user=user).values_list('product_id', flat=True))

    return render(request, 'bloomapp/products/list.html', {
        'products': products,
        'categories': categories,
        'selected_cat': cat_slug,
        'min_price': min_price,
        'max_price': max_price,
        'search_q': q,
        'sort': sort,
        'occasion': occasion,
        'occasion_choices': ['birthday', 'anniversary', 'love', 'wedding', 'graduation', 'sympathy'],
        'user': user,
        'wishlist_ids': wishlist_ids,
    })


def product_detail(request, pk):
    product = get_object_or_404(Product, pk=pk, status='available')
    reviews = product.reviews.select_related('user').order_by('-created_at')
    user = get_current_user(request)

    # Smart recommendations: same primary or extra category, exclude current
    recommendations = (
        Product.objects
        .filter(
            Q(category=product.category) | Q(extra_categories=product.category),
            status='available'
        )
        .exclude(pk=pk)
        .annotate(ocount=Count('orderitem'))
        .order_by('-ocount')[:4]
    )

    star_range = range(1, 6)
    in_wishlist = False
    if user:
        in_wishlist = Wishlist.objects.filter(user=user, product=product).exists()

    return render(request, 'bloomapp/products/detail.html', {
        'product': product,
        'reviews': reviews,
        'recommendations': recommendations,
        'star_range': star_range,
        'user': user,
        'avg_rating': product.avg_rating,
        'in_wishlist': in_wishlist,
    })


@login_required_custom
@require_POST
def submit_review(request, pk):
    product = get_object_or_404(Product, pk=pk)
    user = get_current_user(request)
    rating = _parse_int(request.POST.get('rating'), 5, min_value=1, max_value=5)
    comment = request.POST.get('comment', '').strip()

    if comment:
        # One review per user per product
        Review.objects.update_or_create(
            product=product, user=user,
            defaults={'rating': rating, 'comment': comment}
        )
        messages.success(request, 'Review submitted! Thank you 🌸')

    return redirect('product_detail', pk=pk)


# ──────────────────────────────────────────────────────────────────────────────
# CUSTOM BOUQUET
# ──────────────────────────────────────────────────────────────────────────────

@login_required_custom
def custom_bouquet_view(request):
    user = get_current_user(request)
    if request.method == 'POST':
        flowers = request.POST.get('flowers', 'rose')
        count = _parse_int(request.POST.get('flower_count'), 12, min_value=1, max_value=100)
        wrapping = request.POST.get('wrapping', 'classic')
        message = request.POST.get('message_card', '').strip()[:300]

        # Only accept values from our own lists, never free text from the form.
        wrapping_costs = {'classic': 0, 'rustic': 50, 'luxury': 150, 'minimal': 30}
        if flowers not in dict(FLOWER_CHOICES) or wrapping not in wrapping_costs:
            messages.error(request, 'Please choose a valid flower and wrapping.')
            return redirect('custom_bouquet')

        # Price: base ₹150 + ₹20/flower + wrapping surcharge
        price = 150 + (count * 20) + wrapping_costs[wrapping]
        if message:
            price += 30

        cb = CustomBouquet.objects.create(
            user=user, flowers=flowers, flower_count=count,
            wrapping=wrapping, message_card=message, price=price
        )
        # Add to cart
        CartItem.objects.create(user=user, custom_bouquet=cb, quantity=1)
        messages.success(request, 'Custom bouquet added to cart! 🌺')
        return redirect('cart')

    return render(request, 'bloomapp/bouquet/custom.html', {'user': user})


# ──────────────────────────────────────────────────────────────────────────────
# CART
# ──────────────────────────────────────────────────────────────────────────────

@login_required_custom
def cart_view(request):
    user = get_current_user(request)
    items = CartItem.objects.filter(user=user).select_related('product', 'custom_bouquet')
    subtotal = sum(item.subtotal for item in items)
    return render(request, 'bloomapp/cart/cart.html', {
        'user': user, 'items': items, 'subtotal': subtotal,
    })


@login_required_custom
@require_POST
def add_to_cart(request, pk):
    user = get_current_user(request)
    release_expired_online_orders()
    product = get_object_or_404(Product, pk=pk, status='available')
    qty = _parse_int(request.POST.get('quantity'), 1, min_value=1, max_value=100)

    # ── Stock guard ───────────────────────────────────────────
    if product.stock_quantity <= 0:
        messages.error(request, f'❌ "{product.name}" is out of stock.')
        return redirect(request.META.get('HTTP_REFERER', 'products'))

    # Cap qty to available stock
    current_in_cart = CartItem.objects.filter(user=user, product=product).values_list('quantity', flat=True).first() or 0
    max_addable = product.stock_quantity - current_in_cart
    if qty > max_addable:
        qty = max_addable
        if qty <= 0:
            messages.warning(request, f'⚠️ You already have the maximum available stock of "{product.name}" in your cart.')
            return redirect(request.META.get('HTTP_REFERER', 'products'))
    # ─────────────────────────────────────────────────────────

    item, created = CartItem.objects.get_or_create(user=user, product=product)
    if not created:
        item.quantity += qty
    else:
        item.quantity = qty
    item.save()
    messages.success(request, f'"{product.name}" added to cart! 🛒')

    return redirect(request.META.get('HTTP_REFERER', 'products'))


@login_required_custom
@require_POST
def update_cart(request):
    user = get_current_user(request)
    item_id = _parse_int(request.POST.get('item_id'), None)
    qty = _parse_int(request.POST.get('quantity'), 1, max_value=100)
    item = CartItem.objects.filter(id=item_id, user=user).select_related('product').first() if item_id else None
    if item:
        if qty <= 0:
            item.delete()
        else:
            if item.product and qty > item.product.stock_quantity:
                qty = item.product.stock_quantity
                messages.warning(request, f'⚠️ Only {qty} of "{item.product.name}" in stock.')
            if qty <= 0:
                item.delete()
            else:
                item.quantity = qty
                item.save()
    return redirect('cart')


@login_required_custom
@require_POST
def remove_from_cart(request, item_id):
    user = get_current_user(request)
    CartItem.objects.filter(id=item_id, user=user).delete()
    messages.success(request, 'Item removed from cart.')
    return redirect('cart')


# ──────────────────────────────────────────────────────────────────────────────
# CHECKOUT
# ──────────────────────────────────────────────────────────────────────────────

@login_required_custom
def checkout_view(request):
    user = get_current_user(request)
    items = CartItem.objects.filter(user=user).select_related('product', 'custom_bouquet')
    if not items.exists():
        messages.warning(request, 'Your cart is empty.')
        return redirect('cart')

    subtotal = sum(item.subtotal for item in items)
    addresses = SavedAddress.objects.filter(user=user)

    # Get today+next 7 days for slot picker
    today = date.today()
    available_dates = [today + timedelta(days=i) for i in range(7)]

    return render(request, 'bloomapp/checkout/checkout.html', {
        'user': user, 'items': items, 'subtotal': subtotal,
        'addresses': addresses, 'available_dates': available_dates,
    })


def get_slots_ajax(request):
    """AJAX: return available slots for a given date"""
    date_str = request.GET.get('date')
    try:
        d = datetime.strptime(date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return JsonResponse({'slots': []})

    slots = DeliverySlot.objects.filter(date=d)
    if not slots.exists():
        # Auto-create slots for the day
        slot_times = [
            ('9 AM – 11 AM', '09:00', '11:00'),
            ('11 AM – 1 PM', '11:00', '13:00'),
            ('1 PM – 3 PM', '13:00', '15:00'),
            ('3 PM – 6 PM', '15:00', '18:00'),
            ('6 PM – 9 PM', '18:00', '21:00'),
        ]
        for label, start, end in slot_times:
            DeliverySlot.objects.create(
                date=d, slot_label=label,
                slot_start=start, slot_end=end,
                max_orders=10, booked_count=0
            )
        slots = DeliverySlot.objects.filter(date=d)

    data = [{
        'id': s.id,
        'label': s.slot_label,
        'available': s.is_available,
        'slots_left': s.slots_left,
    } for s in slots]
    return JsonResponse({'slots': data})


def get_delivery_charge_ajax(request):
    """AJAX: return delivery charge for a pincode"""
    pincode = request.GET.get('pincode', '')
    charge = 60  # default
    zone_name = 'Standard'
    for prefix_len in [6, 5, 4, 3]:
        prefix = pincode[:prefix_len]
        zone = DeliveryZone.objects.filter(pincode_prefix=prefix).first()
        if zone:
            charge = float(zone.delivery_charge)
            zone_name = zone.zone_name
            break
    return JsonResponse({'charge': charge, 'zone': zone_name})


def apply_coupon_ajax(request):
    """AJAX: validate coupon code"""
    code = request.GET.get('code', '').strip().upper()
    user = get_current_user(request)
    if not user:
        return JsonResponse({'valid': False, 'message': 'Login required'})

    try:
        coupon = Coupon.objects.get(code=code)
        if coupon.is_valid:
            items = CartItem.objects.filter(user=user)
            subtotal = float(sum(item.subtotal for item in items))
            discount = round(subtotal * coupon.discount_percent / 100, 2)
            return JsonResponse({
                'valid': True,
                'discount_percent': coupon.discount_percent,
                'discount_amount': discount,
                'message': f'{coupon.discount_percent}% off applied!'
            })
        else:
            return JsonResponse({'valid': False, 'message': 'Coupon expired or usage limit reached.'})
    except Coupon.DoesNotExist:
        return JsonResponse({'valid': False, 'message': 'Invalid coupon code.'})


# ──────────────────────────────────────────────────────────────────────────────
# PAYMENT
# ──────────────────────────────────────────────────────────────────────────────

@login_required_custom
def payment_view(request):
    user = get_current_user(request)
    release_expired_online_orders()
    # Retrieve pending order from session
    order_id = request.session.get('pending_order_id')
    if not order_id:
        return redirect('checkout')
    order = get_object_or_404(Order, id=order_id, user=user)
    payment = Payment.objects.filter(order=order).first()
    if order.status == 'cancelled':
        request.session.pop('pending_order_id', None)
        messages.error(request, 'This order expired before payment was completed. Please order again.')
        return redirect('cart')
    if payment and payment.status == 'completed':
        return redirect('order_success', pk=order.id)
    return render(request, 'bloomapp/checkout/payment.html', _payment_page_context(user, order))


def _payment_page_context(user, order):
    return {
        'user': user,
        'order': order,
        'razorpay_order_id': order.razorpay_order_id,
        'amount': int(round(float(order.total_amount) * 100)),  # Razorpay needs paise
        'key': settings.RAZORPAY_KEY_ID,
        'currency': 'INR',
    }


# ──────────────────────────────────────────────────────────────────────────────
# PLACE ORDER
# ──────────────────────────────────────────────────────────────────────────────

@login_required_custom
@require_POST
def place_order(request):
    user = get_current_user(request)
    release_expired_online_orders()
    items = CartItem.objects.filter(user=user).select_related('product', 'custom_bouquet')
    if not items.exists():
        return redirect('cart')

    # ── Server-side Input Validation ─────────────────────────────────────────
    ALLOWED_CITIES_BACKEND = ['anand', 'vadodara', 'ahmedabad', 'surat', 'bharuch', 'nadiad']

    sv_name    = request.POST.get('full_name', '').strip()
    sv_phone   = request.POST.get('phone', '').strip()
    sv_address = request.POST.get('address', '').strip()
    sv_pincode = request.POST.get('pincode', '').strip()
    sv_city    = request.POST.get('city', '').strip()

    if not re.match(r'^[a-zA-Z\s]+$', sv_name):
        messages.error(request, '❌ Invalid input data: Enter a valid name (letters and spaces only).')
        return redirect('checkout')
    if not re.match(r'^[0-9]{10}$', sv_phone):
        messages.error(request, '❌ Invalid input data: Phone must be exactly 10 digits.')
        return redirect('checkout')
    if not re.match(r'^[a-zA-Z0-9\s]+$', sv_address):
        messages.error(request, '❌ Invalid input data: Only letters and numbers allowed in address.')
        return redirect('checkout')
    if not re.match(r'^[0-9]{6}$', sv_pincode):
        messages.error(request, '❌ Invalid input data: Pincode must be exactly 6 digits.')
        return redirect('checkout')
    if sv_city.lower() not in ALLOWED_CITIES_BACKEND:
        messages.error(request, f'❌ Invalid input data: Service not available in "{sv_city}". We serve Anand, Vadodara & Ahmedabad.')
        return redirect('checkout')
    # ─────────────────────────────────────────────────────────────────────────

    # ── City / Service availability check ────────────────────────────────────
    ALLOWED_CITIES = ['anand', 'vadodara', 'ahmedabad', 'surat', 'bharuch', 'nadiad']
    city = sv_city
    if city.lower() not in ALLOWED_CITIES:
        messages.error(request, f'❌ Sorry, Bloomify does not deliver to "{city}" yet.')
        return redirect('checkout')
    # ─────────────────────────────────────────────────────────────────────────


    subtotal = sum(item.subtotal for item in items)

    # ── Stock availability check (friendly early message) ─────
    for item in items:
        if item.product and item.product.stock_quantity < item.quantity:
            messages.error(request, f'❌ "{item.product.name}" only has {item.product.stock_quantity} left in stock. Please update your cart.')
            return redirect('cart')
    # ─────────────────────────────────────────────────────────

    # ── Server-side delivery charge (re-computed, never trusting frontend) ────
    pincode       = sv_pincode
    distance_km   = _parse_float(request.POST.get('distance_km'), 3.0, min_value=0, max_value=500)
    delivery_type = request.POST.get('delivery_type', 'normal')
    zone = None
    for prefix_len in [6, 5, 4, 3]:
        found = DeliveryZone.objects.filter(pincode_prefix=pincode[:prefix_len]).first()
        if found:
            zone = found
            break
    calc          = _calc_delivery(city, distance_km, delivery_type, float(subtotal))
    delivery_charge = calc['delivery_charge']

    payment_mode = request.POST.get('payment_mode', 'cod')
    if payment_mode not in dict(PAYMENT_MODE):
        messages.error(request, 'Please choose a valid payment method.')
        return redirect('checkout')

    coupon_code = request.POST.get('coupon_code', '').strip().upper()
    slot_id     = _parse_int(request.POST.get('slot_id'), None)

    # Everything below happens together or not at all, so a failure can't
    # leave a half-made order or stock that was taken but never sold.
    try:
        with transaction.atomic():
            # Coupon — claim one use only if it is still under its limit
            discount_amount = 0
            coupon_obj = None
            if coupon_code:
                coupon_obj = Coupon.objects.filter(code=coupon_code).first()
                if coupon_obj and coupon_obj.is_valid and Coupon.objects.filter(
                        pk=coupon_obj.pk, used_count__lt=F('max_uses')
                ).update(used_count=F('used_count') + 1):
                    discount_amount = round(float(subtotal) * coupon_obj.discount_percent / 100, 2)
                else:
                    coupon_obj = None

            total = round(float(subtotal) + delivery_charge - discount_amount, 2)

            # Delivery slot — book it only if there is still room
            slot = None
            if slot_id:
                slot = DeliverySlot.objects.filter(id=slot_id).first()
                if slot and not DeliverySlot.objects.filter(
                        pk=slot.pk, booked_count__lt=F('max_orders')
                ).update(booked_count=F('booked_count') + 1):
                    slot = None

            order = Order.objects.create(
                user=user,
                full_name=sv_name,
                email=request.POST.get('email', user.email),
                phone=sv_phone,
                address=sv_address,
                city=sv_city,
                state=request.POST.get('state', ''),
                pincode=pincode,
                delivery_zone=zone,
                delivery_charge=delivery_charge,
                coupon=coupon_obj,
                discount_amount=discount_amount,
                subtotal=float(subtotal),
                total_amount=total,
                payment_mode=payment_mode,
                delivery_slot=slot,
                special_note=request.POST.get('special_note', ''),
                status='placed',
            )

            for item in items:
                OrderItem.objects.create(
                    order=order,
                    product=item.product,
                    custom_bouquet=item.custom_bouquet,
                    quantity=item.quantity,
                    price=item.unit_price,
                    line_total=item.subtotal,
                )
                # Take stock only if enough is left right now (safe if two people buy at once)
                if item.product and not Product.objects.filter(
                        pk=item.product.pk, stock_quantity__gte=item.quantity
                ).update(stock_quantity=F('stock_quantity') - item.quantity):
                    raise _OutOfStock(item.product)

            Payment.objects.create(
                order=order, user=user,
                amount=total, mode=payment_mode,
                status='cod_pending' if payment_mode == 'cod' else 'pending',
            )
    except _OutOfStock as e:
        messages.error(request, f'❌ "{e.product.name}" just sold out. Please update your cart.')
        return redirect('cart')

    # Clear cart
    items.delete()

    if payment_mode == 'cod':
        messages.success(request, 'Order placed successfully! 🌸')
        saved_items = list(OrderItem.objects.filter(order=order).select_related('product'))
        send_order_confirmation_email(order, saved_items)
        return redirect('order_success', pk=order.id)

    # Online payment — create the matching Razorpay order for the exact total
    try:
        client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_SECRET_KEY))
        rzp_order = client.order.create({
            'amount': int(round(total * 100)),  # Razorpay needs paise
            'currency': 'INR',
            'receipt': f'bloomify_order_{order.id}',
            'payment_capture': '1',
        })
    except Exception:
        _release_order(order, payment_status='failed')
        messages.error(request, '❌ Could not start online payment. Please try again or choose Cash on Delivery.')
        return redirect('cart')

    order.razorpay_order_id = rzp_order['id']
    order.save(update_fields=['razorpay_order_id', 'updated_at'])

    request.session['pending_order_id'] = order.id
    return render(request, 'bloomapp/checkout/payment.html', _payment_page_context(user, order))


@login_required_custom
@require_POST
def confirm_payment(request):
    """Called after Razorpay payment success — verifies signature & marks payment done."""
    user = get_current_user(request)

    razorpay_payment_id = request.POST.get('razorpay_payment_id', '')
    razorpay_order_id   = request.POST.get('razorpay_order_id', '')
    razorpay_signature  = request.POST.get('razorpay_signature', '')

    # Find the order by the Razorpay order id that was paid. The signature below
    # proves *that* Razorpay order was paid, and each Razorpay order was created
    # for one of our orders' exact total — so a payment for a cheaper order
    # can't be reused to mark a different order as paid.
    order = None
    if razorpay_order_id:
        order = Order.objects.filter(user=user, razorpay_order_id=razorpay_order_id).first()
    if not order or not razorpay_payment_id or not razorpay_signature:
        messages.error(request, 'Something went wrong. Please contact support.')
        return redirect('home')

    payment = Payment.objects.filter(order=order).first()
    if payment and payment.status == 'completed':
        return redirect('order_success', pk=order.id)

    try:
        client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_SECRET_KEY))
        client.utility.verify_payment_signature({
            'razorpay_order_id':   order.razorpay_order_id,
            'razorpay_payment_id': razorpay_payment_id,
            'razorpay_signature':  razorpay_signature,
        })
    except razorpay.errors.SignatureVerificationError:
        messages.error(request, '❌ Payment verification failed. Contact support.')
        return redirect('home')

    request.session.pop('pending_order_id', None)
    if payment:
        payment.status = 'completed'
        payment.transaction_id = razorpay_payment_id
        payment.save(update_fields=['status', 'transaction_id'])

    if order.status == 'cancelled':
        # Paid after the order had already expired — money must go back by hand.
        if payment:
            payment.status = 'refund_due'
            payment.save(update_fields=['status'])
        messages.error(request, f'⚠️ Your payment for Order #{order.id} arrived after the order expired. '
                                f'We will refund it — please contact support with payment ID {razorpay_payment_id}.')
        return redirect('dashboard')

    saved_items = list(OrderItem.objects.filter(order=order).select_related('product'))
    send_order_confirmation_email(order, saved_items)
    messages.success(request, 'Payment successful! 🎉 Your order is confirmed.')
    return redirect('order_success', pk=order.id)


# ──────────────────────────────────────────────────────────────────────────────
# ORDER TRACKING & SUCCESS
# ──────────────────────────────────────────────────────────────────────────────

@login_required_custom
def order_success(request, pk):
    user = get_current_user(request)
    order = get_object_or_404(Order, pk=pk, user=user)
    return render(request, 'bloomapp/orders/success.html', {'user': user, 'order': order})


@login_required_custom
def order_tracking(request, pk):
    user = get_current_user(request)
    order = get_object_or_404(Order, pk=pk, user=user)
    items = order.items.select_related('product', 'custom_bouquet')
    steps = [
        ('placed', 'Order Placed', 'Your order has been confirmed.'),
        ('packed', 'Packed', 'Your bouquet is being carefully packed.'),
        ('out_for_delivery', 'Out for Delivery', 'On the way to you!'),
        ('delivered', 'Delivered', 'Enjoy your beautiful flowers! 🌸'),
    ]
    return render(request, 'bloomapp/orders/tracking.html', {
        'user': user, 'order': order, 'items': items, 'steps': steps,
    })


# ──────────────────────────────────────────────────────────────────────────────
# USER DASHBOARD
# ──────────────────────────────────────────────────────────────────────────────

@login_required_custom
def user_dashboard(request):
    user = get_current_user(request)
    orders = Order.objects.filter(user=user).order_by('-created_at')
    addresses = SavedAddress.objects.filter(user=user)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'update_profile':
            user.full_name = request.POST.get('full_name', user.full_name)
            user.phone = request.POST.get('phone', user.phone)
            new_pass = request.POST.get('new_password', '')
            if new_pass:
                user.password = make_password(new_pass)
            user.save()
            request.session['user_name'] = user.full_name
            messages.success(request, 'Profile updated! ✅')
            return redirect('dashboard')

        elif action == 'add_address':
            SavedAddress.objects.create(
                user=user,
                label=request.POST.get('label', 'Home'),
                full_name=request.POST.get('addr_name', ''),
                phone=request.POST.get('addr_phone', ''),
                address=request.POST.get('addr_street', ''),
                city=request.POST.get('addr_city', ''),
                state=request.POST.get('addr_state', ''),
                pincode=request.POST.get('addr_pincode', ''),
            )
            messages.success(request, 'Address saved! 📍')
            return redirect('dashboard')

        elif action == 'delete_address':
            addr_id = request.POST.get('address_id')
            SavedAddress.objects.filter(id=addr_id, user=user).delete()
            messages.success(request, 'Address removed.')
            return redirect('dashboard')

    tab = request.GET.get('tab', 'orders')
    return render(request, 'bloomapp/dashboard/dashboard.html', {
        'user': user, 'orders': orders, 'addresses': addresses, 'tab': tab,
    })


# ──────────────────────────────────────────────────────────────────────────────
# ADMIN PANEL
# ──────────────────────────────────────────────────────────────────────────────

def admin_login(request):
    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        password = request.POST.get('password', '')
        try:
            user = User.objects.get(email=email)
            if check_password(password, user.password) and user.is_staff_member():
                request.session['admin_id'] = user.id
                request.session['admin_name'] = user.full_name
                request.session['admin_role'] = user.role
                messages.success(request, f'Welcome, {user.full_name}!')
                return redirect('admin_dashboard')
            else:
                messages.error(request, 'Invalid credentials or insufficient permissions.')
        except User.DoesNotExist:
            messages.error(request, 'No admin account found.')

    return render(request, 'bloomapp/admin_panel/login.html')


def admin_logout(request):
    request.session.pop('admin_id', None)
    request.session.pop('admin_name', None)
    request.session.pop('admin_role', None)
    return redirect('admin_login')


@admin_required
def admin_dashboard(request):
    admin_user = request.admin_user
    release_expired_online_orders()
    is_staff = admin_user.role == 'staff'

    # KPIs — staff only see order counts, not revenue or user counts
    total_orders   = Order.objects.count()
    pending_orders = Order.objects.filter(status='placed').count()
    packed_orders  = Order.objects.filter(status='packed').count()
    out_orders     = Order.objects.filter(status='out_for_delivery').count()
    recent_orders  = Order.objects.order_by('-created_at')[:5]

    # Admin-only KPIs
    total_users   = User.objects.filter(role='user').count() if not is_staff else None
    total_revenue = (Order.objects.aggregate(r=Sum('total_amount'))['r'] or 0) if not is_staff else None

    # ── Stock Alerts ─────────────────────────────────────────────────
    out_of_stock = Product.objects.filter(status='available', stock_quantity=0).order_by('name')
    low_stock    = Product.objects.filter(status='available', stock_quantity__gt=0, stock_quantity__lte=5).order_by('stock_quantity')

    return render(request, 'bloomapp/admin_panel/dashboard.html', {
        'admin_user':    admin_user,
        'is_staff':      is_staff,
        'total_orders':  total_orders,
        'pending_orders': pending_orders,
        'packed_orders': packed_orders,
        'out_orders':    out_orders,
        'recent_orders': recent_orders,
        'total_users':   total_users,
        'total_revenue': total_revenue,
        'out_of_stock':  out_of_stock,
        'low_stock':     low_stock,
    })



@admin_required
def admin_messages(request):
    if request.method == 'POST':
        msg_id = request.POST.get('msg_id')
        if msg_id:
            ContactMessage.objects.filter(id=msg_id).update(is_read=True)
    msgs = ContactMessage.objects.all()
    return render(request, 'bloomapp/admin_panel/messages.html', {
        'admin_user':    request.admin_user,
        'is_staff':      request.admin_user.role == 'staff',
        'messages_list': msgs,
        'unread_count':  msgs.filter(is_read=False).count(),
    })


@admin_required
def admin_analytics_api(request):
    """JSON endpoint for Chart.js — admin only"""
    if not request.admin_user.is_admin():
        return JsonResponse({'error': 'Forbidden'}, status=403)
    today = timezone.now().date()

    # Revenue last 7 days
    revenue_data = []
    labels = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        rev = Order.objects.filter(created_at__date=d).aggregate(s=Sum('total_amount'))['s'] or 0
        revenue_data.append(float(rev))
        labels.append(d.strftime('%d %b'))

    # Orders by category
    cats = Category.objects.filter(status='available')
    cat_labels = []
    cat_data = []
    for cat in cats:
        count = OrderItem.objects.filter(product__category=cat).count()
        cat_labels.append(cat.name)
        cat_data.append(count)

    # User signups last 7 days
    signup_data = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        count = User.objects.filter(created_at__date=d).count()
        signup_data.append(count)

    return JsonResponse({
        'revenue': {'labels': labels, 'data': revenue_data},
        'categories': {'labels': cat_labels, 'data': cat_data},
        'signups': {'labels': labels, 'data': signup_data},
    })


@admin_required
def admin_products(request):
    admin_user = request.admin_user
    categories = Category.objects.all()
    products = Product.objects.select_related('category').order_by('-created_at')
    return render(request, 'bloomapp/admin_panel/products.html', {
        'admin_user': admin_user,
        'products': products,
        'categories': categories,
        'is_staff': admin_user.role == 'staff',
    })


@admin_required
@require_POST
def admin_product_add(request):
    # ❌ Staff cannot add products
    if not request.admin_user.is_admin():
        messages.error(request, '🚫 Staff cannot add products.')
        return redirect('admin_products')
    name = request.POST.get('name')
    cat_id = request.POST.get('category')
    description = request.POST.get('description', '')
    original_price = request.POST.get('original_price')
    price = request.POST.get('price')
    stock = request.POST.get('stock_quantity', 10)
    flowers = request.POST.get('flowers', '')
    occasion_tags = request.POST.get('occasion_tags', '')
    is_featured = request.POST.get('is_featured') == 'on'
    status = request.POST.get('status', 'available')

    product = Product.objects.create(
        name=name,
        category_id=cat_id,
        description=description,
        original_price=original_price,
        price=price,
        stock_quantity=stock,
        flowers=flowers,
        occasion_tags=occasion_tags,
        is_featured=is_featured,
        status=status,
    )
    if 'image_main' in request.FILES:
        product.image_main = request.FILES['image_main']
    if 'image_2' in request.FILES:
        product.image_2 = request.FILES['image_2']
    if 'image_3' in request.FILES:
        product.image_3 = request.FILES['image_3']
    product.save()
    # Save extra categories (multi-select)
    extra_cat_ids = request.POST.getlist('extra_categories')
    product.extra_categories.set(extra_cat_ids)
    messages.success(request, 'Product added successfully!')
    return redirect('admin_products')


@admin_required
@require_POST
def admin_product_edit(request, pk):
    # ❌ Staff cannot edit products
    if not request.admin_user.is_admin():
        messages.error(request, '🚫 Staff cannot edit products.')
        return redirect('admin_products')
    product = get_object_or_404(Product, pk=pk)
    product.name = request.POST.get('name', product.name)
    product.category_id = request.POST.get('category', product.category_id)
    product.description = request.POST.get('description', product.description)
    product.original_price = request.POST.get('original_price', product.original_price)
    product.price = request.POST.get('price', product.price)
    product.stock_quantity = request.POST.get('stock_quantity', product.stock_quantity)
    product.flowers = request.POST.get('flowers', product.flowers)
    product.occasion_tags = request.POST.get('occasion_tags', product.occasion_tags)
    product.is_featured = request.POST.get('is_featured') == 'on'
    product.status = request.POST.get('status', product.status)
    if 'image_main' in request.FILES:
        product.image_main = request.FILES['image_main']
    product.save()
    # Save extra categories (multi-select; empty list clears all)
    extra_cat_ids = request.POST.getlist('extra_categories')
    product.extra_categories.set(extra_cat_ids)
    messages.success(request, 'Product updated!')
    return redirect('admin_products')


@admin_required
@require_POST
def admin_product_delete(request, pk):
    # ❌ Staff cannot delete products
    if not request.admin_user.is_admin():
        messages.error(request, '🚫 Staff cannot delete products.')
        return redirect('admin_products')
    product = get_object_or_404(Product, pk=pk)
    product.delete()
    messages.success(request, 'Product deleted.')
    return redirect('admin_products')


@admin_required
def admin_orders(request):
    admin_user = request.admin_user
    release_expired_online_orders()
    orders = Order.objects.select_related('user', 'delivery_slot').prefetch_related('items__product').order_by('-created_at')
    status_filter = request.GET.get('status', '')
    if status_filter:
        orders = orders.filter(status=status_filter)
    from .models import ORDER_STATUS
    return render(request, 'bloomapp/admin_panel/orders.html', {
        'admin_user': admin_user,
        'orders': orders,
        'status_choices': ORDER_STATUS,
        'status_filter': status_filter,
        'is_staff': admin_user.role == 'staff',
    })


@admin_required
@require_POST
def admin_order_update(request, pk):
    order = get_object_or_404(Order, pk=pk)
    order.status = request.POST.get('status', order.status)
    order.save()
    messages.success(request, f'Order #{order.id} status updated.')
    return redirect('admin_orders')


@admin_required
def admin_users(request):
    admin_user = request.admin_user
    if not admin_user.is_admin():
        messages.error(request, 'Admin access required.')
        return redirect('admin_dashboard')
    users = User.objects.all().order_by('-created_at')
    staff_count = users.filter(role__in=['admin', 'staff']).count()
    return render(request, 'bloomapp/admin_panel/users.html', {
        'admin_user': admin_user,
        'users': users,
        'staff_count': staff_count,
    })


@admin_required
def admin_coupons(request):
    admin_user = request.admin_user
    if not admin_user.is_admin():
        messages.error(request, 'Admin access required.')
        return redirect('admin_dashboard')

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'create':
            Coupon.objects.create(
                code=request.POST.get('code', '').upper(),
                discount_percent=request.POST.get('discount_percent', 10),
                max_uses=request.POST.get('max_uses', 100),
                expiry=request.POST.get('expiry'),
                is_active=True,
            )
            messages.success(request, 'Coupon created!')
        elif action == 'toggle':
            c = Coupon.objects.get(id=request.POST.get('coupon_id'))
            c.is_active = not c.is_active
            c.save()
            messages.success(request, 'Coupon status toggled.')
        elif action == 'delete':
            Coupon.objects.filter(id=request.POST.get('coupon_id')).delete()
            messages.success(request, 'Coupon deleted.')
        return redirect('admin_coupons')

    coupons = Coupon.objects.order_by('-created_at')
    return render(request, 'bloomapp/admin_panel/coupons.html', {
        'admin_user': admin_user, 'coupons': coupons,
    })


# ──────────────────────────────────────────────────────────────────────────────
# SALES REPORT
# ──────────────────────────────────────────────────────────────────────────────

def _get_report_queryset(request):
    """Shared filter logic used by both the HTML page and CSV download."""
    orders = Order.objects.select_related('user', 'coupon').prefetch_related('items__product')

    date_from = request.GET.get('date_from', '')
    date_to   = request.GET.get('date_to', '')
    status    = request.GET.get('status', '')
    payment   = request.GET.get('payment', '')

    if date_from:
        try:
            orders = orders.filter(created_at__date__gte=datetime.strptime(date_from, '%Y-%m-%d').date())
        except ValueError:
            pass
    if date_to:
        try:
            orders = orders.filter(created_at__date__lte=datetime.strptime(date_to, '%Y-%m-%d').date())
        except ValueError:
            pass
    if status:
        orders = orders.filter(status=status)
    if payment:
        orders = orders.filter(payment_mode=payment)

    return orders.order_by('-created_at')


@admin_required
def admin_sales_report(request):
    admin_user = request.admin_user
    if not admin_user.is_admin():
        messages.error(request, 'Admin access required.')
        return redirect('admin_dashboard')

    orders = _get_report_queryset(request)

    # ── Summary Aggregates ────────────────────────────────────────────────────
    agg = orders.aggregate(
        total_revenue  = Sum('total_amount'),
        total_subtotal = Sum('subtotal'),
        total_discount = Sum('discount_amount'),
        total_delivery = Sum('delivery_charge'),
        total_orders   = Count('id'),
    )
    total_revenue  = agg['total_revenue']  or 0
    total_subtotal = agg['total_subtotal'] or 0
    total_discount = agg['total_discount'] or 0
    total_delivery = agg['total_delivery'] or 0
    total_orders   = agg['total_orders']   or 0
    avg_order_val  = round(total_revenue / total_orders, 2) if total_orders else 0

    # ── Orders by Status ──────────────────────────────────────────────────────
    status_breakdown = (
        orders.values('status')
              .annotate(count=Count('id'), revenue=Sum('total_amount'))
              .order_by('-count')
    )

    # ── Orders by Payment Mode ────────────────────────────────────────────────
    payment_breakdown = (
        orders.values('payment_mode')
              .annotate(count=Count('id'), revenue=Sum('total_amount'))
              .order_by('-count')
    )

    # ── Top 10 Products ───────────────────────────────────────────────────────
    from .models import OrderItem
    top_products = (
        OrderItem.objects
        .filter(order__in=orders)
        .values('product__name')
        .annotate(units_sold=Sum('quantity'), revenue=Sum('line_total'))
        .order_by('-revenue')[:10]
    )

    # ── Daily Revenue (last 30 days if no date filter) ────────────────────────
    daily = (
        orders.extra(select={'day': "DATE(created_at)"})
              .values('day')
              .annotate(revenue=Sum('total_amount'), count=Count('id'))
              .order_by('day')
    )

    # Active filter values for template
    filters = {
        'date_from': request.GET.get('date_from', ''),
        'date_to':   request.GET.get('date_to', ''),
        'status':    request.GET.get('status', ''),
        'payment':   request.GET.get('payment', ''),
    }

    return render(request, 'bloomapp/admin_panel/sales_report.html', {
        'admin_user':        admin_user,
        'orders':            orders[:200],    # cap HTML table at 200 rows; CSV has no limit
        'filters':           filters,
        'total_revenue':     total_revenue,
        'total_subtotal':    total_subtotal,
        'total_discount':    total_discount,
        'total_delivery':    total_delivery,
        'total_orders':      total_orders,
        'avg_order_val':     avg_order_val,
        'status_breakdown':  status_breakdown,
        'payment_breakdown': payment_breakdown,
        'top_products':      top_products,
        'daily':             daily,
        'order_statuses':    ['placed', 'packed', 'out_for_delivery', 'delivered', 'cancelled'],
        'payment_modes':     ['cod', 'upi', 'card'],
    })


@admin_required
def admin_sales_report_csv(request):
    """Stream a CSV file of filtered orders — works with the same filters as the HTML page."""
    admin_user = request.admin_user
    if not admin_user.is_admin():
        messages.error(request, 'Admin access required.')
        return redirect('admin_dashboard')

    orders = _get_report_queryset(request)

    # Build filename from date filters
    f_from = request.GET.get('date_from', '') or 'all'
    f_to   = request.GET.get('date_to', '')   or 'all'
    filename = f"bloomify_sales_{f_from}_to_{f_to}.csv"

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)

    # Header row
    writer.writerow([
        'Order ID', 'Date', 'Customer Name', 'Email', 'Phone',
        'City', 'Pincode', 'Payment Mode', 'Status',
        'Subtotal (₹)', 'Delivery Charge (₹)', 'Discount (₹)', 'Total Amount (₹)',
        'Coupon Code', 'Items',
    ])

    for order in orders:
        items_str = ' | '.join(
            f"{item.product.name if item.product else 'Custom Bouquet'} x{item.quantity}"
            for item in order.items.all()
        )
        writer.writerow([
            f'#{order.id}',
            order.created_at.strftime('%d-%m-%Y %H:%M'),
            order.full_name,
            order.email,
            order.phone,
            order.city,
            order.pincode,
            order.get_payment_mode_display(),
            order.status_display,
            order.subtotal,
            order.delivery_charge,
            order.discount_amount,
            order.total_amount,
            order.coupon.code if order.coupon else '—',
            items_str,
        ])

    return response


@admin_required
def admin_sales_report_print(request):
    """
    Standalone print-friendly view — opens in a new tab and auto-triggers
    window.print(). The browser's 'Save as PDF' produces a perfect, fully
    coloured PDF because the browser resolves all CSS itself.
    """
    admin_user = request.admin_user
    if not admin_user.is_admin():
        return redirect('admin_dashboard')

    orders = _get_report_queryset(request)

    agg = orders.aggregate(
        total_revenue  = Sum('total_amount'),
        total_subtotal = Sum('subtotal'),
        total_discount = Sum('discount_amount'),
        total_delivery = Sum('delivery_charge'),
        total_orders   = Count('id'),
    )
    total_revenue  = agg['total_revenue']  or 0
    total_subtotal = agg['total_subtotal'] or 0
    total_discount = agg['total_discount'] or 0
    total_delivery = agg['total_delivery'] or 0
    total_orders   = agg['total_orders']   or 0
    avg_order_val  = round(float(total_revenue) / total_orders, 2) if total_orders else 0

    status_breakdown = (
        orders.values('status')
              .annotate(count=Count('id'), revenue=Sum('total_amount'))
              .order_by('-count')
    )
    payment_breakdown = (
        orders.values('payment_mode')
              .annotate(count=Count('id'), revenue=Sum('total_amount'))
              .order_by('-count')
    )
    from .models import OrderItem
    top_products = (
        OrderItem.objects
        .filter(order__in=orders)
        .values('product__name')
        .annotate(units_sold=Sum('quantity'), revenue=Sum('line_total'))
        .order_by('-revenue')[:10]
    )

    filters = {
        'date_from': request.GET.get('date_from', ''),
        'date_to':   request.GET.get('date_to', ''),
        'status':    request.GET.get('status', ''),
        'payment':   request.GET.get('payment', ''),
    }

    return render(request, 'bloomapp/admin_panel/sales_report_print.html', {
        'admin_user':        admin_user,
        'orders':            orders,
        'filters':           filters,
        'total_revenue':     total_revenue,
        'total_subtotal':    total_subtotal,
        'total_discount':    total_discount,
        'total_delivery':    total_delivery,
        'total_orders':      total_orders,
        'avg_order_val':     avg_order_val,
        'status_breakdown':  status_breakdown,
        'payment_breakdown': payment_breakdown,
        'top_products':      top_products,
        'order_statuses':    ['placed', 'packed', 'out_for_delivery', 'delivered', 'cancelled'],
        'payment_modes':     ['cod', 'upi', 'card'],
    })


# ──────────────────────────────────────────────────────────────────────────────
# WISHLIST
# ──────────────────────────────────────────────────────────────────────────────

@login_required_custom
def wishlist_view(request):
    user = get_current_user(request)
    items = Wishlist.objects.filter(user=user).select_related('product')
    return render(request, 'bloomapp/wishlist/wishlist.html', {
        'user': user, 'items': items,
    })


@login_required_custom
@require_POST
def toggle_wishlist(request, pk):
    user    = get_current_user(request)
    product = get_object_or_404(Product, pk=pk)
    obj, created = Wishlist.objects.get_or_create(user=user, product=product)
    if not created:
        obj.delete()
        in_wishlist = False
        msg = f'"{product.name}" removed from wishlist.'
    else:
        in_wishlist = True
        msg = f'"{product.name}" added to wishlist! ♥'
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'in_wishlist': in_wishlist, 'message': msg})
    messages.success(request, msg)
    return redirect(request.META.get('HTTP_REFERER', 'products'))


# ──────────────────────────────────────────────────────────────────────────────
# NEWSLETTER
# ──────────────────────────────────────────────────────────────────────────────

@require_POST
def newsletter_subscribe(request):
    email = request.POST.get('email', '').strip().lower()
    if not email or '@' not in email:
        return JsonResponse({'ok': False, 'message': 'Invalid email address.'}, status=400)
    _, created = NewsletterSubscriber.objects.get_or_create(email=email)
    if created:
        return JsonResponse({'ok': True, 'message': 'Subscribed! Thank you 🌸'})
    return JsonResponse({'ok': True, 'message': "You're already subscribed!"})


# ──────────────────────────────────────────────────────────────────────────────
# SEARCH AUTOCOMPLETE
# ──────────────────────────────────────────────────────────────────────────────

def search_autocomplete(request):
    q = request.GET.get('q', '').strip()
    if len(q) < 2:
        return JsonResponse({'results': []})
    products = Product.objects.filter(
        status='available'
    ).filter(
        Q(name__icontains=q) | Q(flowers__icontains=q) | Q(occasion_tags__icontains=q)
    )[:8]
    results = [{
        'id': p.pk,
        'name': p.name,
        'price': str(p.price),
        'image': p.get_image,
        'url': f'/products/{p.pk}/',
        'category': p.category.name,
    } for p in products]
    return JsonResponse({'results': results})


# ──────────────────────────────────────────────────────────────────────────────
# ORDER CANCELLATION
# ──────────────────────────────────────────────────────────────────────────────

@login_required_custom
@require_POST
def cancel_order(request, pk):
    user  = get_current_user(request)
    order = get_object_or_404(Order, pk=pk, user=user)
    if order.status != 'placed':
        messages.error(request, 'Only orders with status “Placed” can be cancelled.')
        return redirect('dashboard')
    payment = Payment.objects.filter(order=order).first()
    new_payment_status = None
    if payment and payment.status == 'pending':
        new_payment_status = 'cancelled'
    elif payment and payment.status == 'completed':
        new_payment_status = 'refund_due'
    _release_order(order, payment_status=new_payment_status)
    messages.success(request, f'Order #{order.id} has been cancelled. Stock restored.')
    return redirect('dashboard')
