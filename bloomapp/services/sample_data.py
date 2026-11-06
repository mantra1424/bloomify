"""
Sample shop activity for the public demo: customers, orders, reviews, messages.

Without it the admin dashboard, charts, reports and the demo customer's account
are empty. Everything is made up: sample customers use example.com addresses and
can't log in. Running it again creates nothing new; it only moves the sample
orders forward in time so the "last 7 days" charts still have data.
"""

import random
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from bloomapp.models import (
    ContactMessage,
    CustomBouquet,
    NewsletterSubscriber,
    Order,
    OrderItem,
    Payment,
    Product,
    Review,
    SavedAddress,
    User,
    Wishlist,
)
from bloomapp.services import pricing

# (full name, phone, street, city, pincode)
SAMPLE_CUSTOMERS = [
    ('Riya Shah', '9825012345', '14, Shreeji Society, Vallabh Vidyanagar', 'Anand', '388120'),
    ('Aarav Patel', '9898023456', 'B-302, Sun Residency, Alkapuri', 'Vadodara', '390007'),
    ('Kavya Mehta', '9724034567', '7, Shanti Kunj, Satellite Road', 'Ahmedabad', '380015'),
    ('Ishaan Desai', '9909045678', '21, Green Park, Adajan', 'Surat', '395009'),
    ('Ananya Joshi', '9879056789', '5, Laxmi Nagar, Zadeshwar Road', 'Bharuch', '392011'),
    ('Vihaan Trivedi', '9428067890', '33, Santram Society, College Road', 'Nadiad', '387001'),
    ('Diya Bhatt', '9737078901', 'A-12, Shivam Flats, Navrangpura', 'Ahmedabad', '380009'),
    ('Arjun Rana', '9512089012', '9, Rajmahal Road, Mandvi', 'Vadodara', '390001'),
    ('Saanvi Chauhan', '9601090123', '18, Pushpak Society, Piplag Road', 'Anand', '388001'),
    ('Kabir Parmar', '9824101234', '4, Vesu Main Road, Vesu', 'Surat', '395007'),
]

REVIEWS = [
    (5, 'Arrived right on time and looked even better than the photo. My mother loved it.'),
    (5, 'Fresh flowers that lasted over a week. Will order again for every birthday.'),
    (4, 'Beautiful bouquet and neatly wrapped. Delivery was about 30 minutes late.'),
    (5, 'The midnight delivery made the surprise perfect. Thank you!'),
    (4, 'Lovely colours and a sweet message card. Slightly smaller than I expected.'),
    (5, 'Ordered for our anniversary. Everything was fresh and the rider was very polite.'),
    (3, 'Flowers were nice but one stem was bent. Support replaced it the next day.'),
    (5, 'Great value with the coupon. The custom note was printed perfectly.'),
]

MESSAGES = [
    ('Kavya Mehta', 'Bulk order', 'Do you take orders for 40 table bouquets for a wedding in December?', False),
    ('Arjun Rana', 'Delivery', 'Can I choose a delivery time for a surprise at the office tomorrow?', False),
    ('Riya Shah', 'Feedback', 'Just wanted to say the tulips were gorgeous. Thank you!', True),
]

CARD_NOTES = ['Happy birthday, Maa!', 'Happy anniversary, love.', 'Congratulations on the new job!', '']


def sample_email(name):
    return name.lower().replace(' ', '.') + '@example.com'


def seed_sample_activity(log=print):
    """Create the sample activity once; on later runs just keep its dates recent."""
    customers = list(User.objects.filter(email__in=[sample_email(c[0]) for c in SAMPLE_CUSTOMERS]))
    if Order.objects.filter(user__in=customers).exists():
        moved = _keep_dates_recent(customers)
        note = f' (dates moved forward {moved} day{"s" if moved > 1 else ""})' if moved else ''
        log(f'  ⏭  Sample activity already exists{note}')
        return
    if not Product.objects.exists():
        log('  ⏭  No products yet, skipping sample activity')
        return
    with transaction.atomic():
        _create(random.Random(2026), log)  # noqa: S311 (made-up demo data, not security)


def _keep_dates_recent(customers):
    """Shift sample orders, reviews and sign-ups so the newest sample order is from today."""
    newest = Order.objects.filter(user__in=customers).order_by('-created_at').first()
    days = (timezone.localdate() - timezone.localtime(newest.created_at).date()).days
    if days > 0:
        shift = timedelta(days=days)
        Order.objects.filter(user__in=customers).update(created_at=F('created_at') + shift)
        Review.objects.filter(user__in=customers).update(created_at=F('created_at') + shift)
        User.objects.filter(pk__in=[c.pk for c in customers]).update(created_at=F('created_at') + shift)
    return days


# Days ago each sample customer signed up: most last month, a few this week.
SIGNUP_DAYS_AGO = [40, 36, 31, 27, 22, 17, 12, 6, 4, 2]


def _create(rng, log):
    now = timezone.now()
    products = list(Product.objects.filter(status='available').order_by('id'))

    customers = []
    for (name, phone, street, city, pincode), days_ago in zip(SAMPLE_CUSTOMERS, SIGNUP_DAYS_AGO, strict=True):
        user, _ = User.objects.get_or_create(
            email=sample_email(name), defaults={'full_name': name, 'phone': phone, 'role': 'user'}
        )
        user.set_unusable_password()
        user.save(update_fields=['password'])
        _set_created(user, _time_on(rng, now, days_ago))
        customers.append((user, street, city, pincode, days_ago))

    # ── Orders: a month of history, newest ones still on their way ─────────
    orders = 0
    for days_ago in range(30, -1, -1):
        signed_up = [c for c in customers if c[4] > days_ago]
        for _ in range(rng.choice([0, 1, 1, 2]) if days_ago > 6 else rng.choice([1, 2, 2])):
            user, street, city, pincode, _ = rng.choice(signed_up)
            created = _time_on(rng, now, days_ago)
            _make_order(rng, user, street, city, pincode, products, created, _status_for(rng, days_ago))
            orders += 1

    demo = User.objects.filter(email='demo@bloomify.com').first()
    if demo:
        _fill_demo_account(rng, demo, products, now)

    # ── Reviews: two or three per bouquet ─────────────────────────────────
    reviews = 0
    for product in products:
        for user, *_ in rng.sample(customers, rng.choice([2, 3])):
            rating, comment = rng.choice(REVIEWS)
            review = Review.objects.create(product=product, user=user, rating=rating, comment=comment)
            _set_created(review, _time_on(rng, now, rng.randint(1, 28)))
            reviews += 1

    for name, subject, message, is_read in MESSAGES:
        ContactMessage.objects.create(
            name=name, email=sample_email(name), subject=subject, message=message, is_read=is_read
        )
    for user, *_ in customers[:6]:
        NewsletterSubscriber.objects.get_or_create(email=user.email)

    counts = f'{len(customers)} customers, {orders} orders, {reviews} reviews, {len(MESSAGES)} messages'
    log(f'  ✅ Sample activity: {counts}')


def _status_for(rng, days_ago):
    if days_ago == 0:
        return rng.choice(['placed', 'placed', 'packed'])
    if days_ago == 1:
        return rng.choice(['packed', 'out_for_delivery'])
    return 'cancelled' if rng.random() < 0.08 else 'delivered'


def _make_order(rng, user, street, city, pincode, products, created, status, custom=None):
    if custom is None and rng.random() < 0.15:
        custom = _custom_bouquet(rng, user)
    picks = [(None, custom)] if custom else [(p, None) for p in rng.sample(products, rng.choice([1, 1, 2]))]
    lines = []
    for product, bouquet in picks:
        qty = 1 if bouquet else rng.choice([1, 1, 1, 2])
        lines.append((product, bouquet, qty, product.price if product else bouquet.price))
    subtotal = sum((price * qty for *_, qty, price in lines), Decimal('0'))
    delivery_type = rng.choice(['normal', 'normal', 'sameday', 'midnight'])
    charge = Decimal(pricing.calc_delivery(city, 3.0, delivery_type, float(subtotal))['delivery_charge'])
    mode = rng.choice(['online', 'online', 'cod'])

    order = Order.objects.create(
        user=user,
        full_name=user.full_name,
        email=user.email,
        phone=user.phone,
        address=street,
        city=city,
        state='Gujarat',
        pincode=pincode,
        delivery_charge=charge,
        subtotal=subtotal,
        total_amount=subtotal + charge,
        payment_mode=mode,
        status=status,
        special_note=rng.choice(['', '', 'Please call before delivery.', 'Leave with the security guard.']),
    )
    for product, bouquet, qty, price in lines:
        OrderItem.objects.create(
            order=order, product=product, custom_bouquet=bouquet, quantity=qty, price=price, line_total=price * qty
        )
    Payment.objects.create(
        order=order,
        user=user,
        amount=order.total_amount,
        mode=mode,
        transaction_id=f'pay_SAMPLE{order.id:06d}' if mode == 'online' and status != 'cancelled' else '',
        status=_payment_status(mode, status),
    )
    _set_created(order, created)
    return order


def _payment_status(mode, status):
    if status == 'cancelled':
        return 'cancelled'
    if mode == 'online':
        return 'completed'
    return 'completed' if status == 'delivered' else 'cod_pending'


def _custom_bouquet(rng, user):
    flower = rng.choice(list(pricing.FLOWER_SURCHARGES))
    count = rng.choice([12, 18, 24])
    wrapping = rng.choice(list(pricing.WRAPPING_COSTS))
    note = rng.choice(CARD_NOTES)
    return CustomBouquet.objects.create(
        user=user,
        flowers=flower,
        flower_count=count,
        wrapping=wrapping,
        message_card=note,
        price=pricing.custom_bouquet_price(count, wrapping, bool(note), flower),
    )


def _fill_demo_account(rng, demo, products, now):
    """Give the demo login a saved address, a wishlist and orders at every stage."""
    street, city, pincode = '12, Rose Villa, Mota Bazaar', 'Anand', '388001'
    SavedAddress.objects.get_or_create(
        user=demo,
        label='Home',
        defaults={
            'full_name': demo.full_name,
            'phone': demo.phone,
            'address': street,
            'city': city,
            'state': 'Gujarat',
            'pincode': pincode,
            'is_default': True,
        },
    )
    for product in products[:3]:
        Wishlist.objects.get_or_create(user=demo, product=product)
    if Order.objects.filter(user=demo).exists():
        return
    _make_order(rng, demo, street, city, pincode, products, _time_on(rng, now, 18), 'delivered')
    _make_order(
        rng,
        demo,
        street,
        city,
        pincode,
        products,
        _time_on(rng, now, 6),
        'delivered',
        custom=_custom_bouquet(rng, demo),
    )
    _make_order(rng, demo, street, city, pincode, products, _time_on(rng, now, 0), 'out_for_delivery')


def _time_on(rng, now, days_ago):
    """A shop-hours time on the calendar day `days_ago` days back, never later than now."""
    local = timezone.localtime(now)
    when = local.replace(hour=rng.randint(9, 20), minute=rng.randint(0, 59), second=0, microsecond=0)
    when -= timedelta(days=days_ago)
    if when > now:  # today, before that hour: a few minutes ago instead (but still today)
        day_start = local.replace(hour=0, minute=0, second=0, microsecond=0)
        when = max(now - timedelta(minutes=rng.randint(5, 90)), day_start)
    return when


def _set_created(obj, when):
    """created_at is filled in automatically on save, so set the sample date afterwards."""
    type(obj).objects.filter(pk=obj.pk).update(created_at=when)
