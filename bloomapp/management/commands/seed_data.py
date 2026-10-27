"""
Seed command — populates Bloomify with demo data.
Usage: python manage.py seed_data
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.hashers import make_password
from django.utils import timezone
from datetime import date, timedelta
from bloomapp.models import (
    User, Category, Product, Coupon, DeliveryZone
)


class Command(BaseCommand):
    help = 'Seed the database with demo data for Bloomify'

    def handle(self, *args, **kwargs):
        self.stdout.write('🌸 Seeding Bloomify demo data...')

        # ── Admin User ──────────────────────────────────────────────
        admin, created = User.objects.get_or_create(
            email='admin@bloomify.com',
            defaults={
                'full_name': 'Bloomify Admin',
                'password': make_password('admin123'),
                'phone': '9999999999',
                'role': 'admin',
            }
        )
        if created:
            self.stdout.write('  ✅ Admin user created  →  admin@bloomify.com / admin123')
        else:
            self.stdout.write('  ⏭  Admin user already exists')

        # ── Staff User ──────────────────────────────────────────────
        staff, _ = User.objects.get_or_create(
            email='staff@bloomify.com',
            defaults={
                'full_name': 'Bloomify Staff',
                'password': make_password('staff123'),
                'phone': '8888888888',
                'role': 'staff',
            }
        )
        self.stdout.write('  ✅ Staff user  →  staff@bloomify.com / staff123')

        # ── Demo Customer ────────────────────────────────────────────
        customer, _ = User.objects.get_or_create(
            email='demo@bloomify.com',
            defaults={
                'full_name': 'Demo Customer',
                'password': make_password('demo123'),
                'phone': '7777777777',
                'role': 'user',
            }
        )
        self.stdout.write('  ✅ Demo user  →  demo@bloomify.com / demo123')

        # ── Categories ───────────────────────────────────────────────
        cats_data = [
            ('Birthday', 'birthday', '🎂'),
            ('Anniversary', 'anniversary', '💍'),
            ('Love & Romance', 'love', '❤️'),
            ('Wedding', 'wedding', '💐'),
            ('Sympathy', 'sympathy', '🕊️'),
            ('Thank You', 'thank-you', '🌻'),
        ]
        categories = {}
        for name, slug, icon in cats_data:
            cat, _ = Category.objects.get_or_create(
                slug=slug,
                defaults={'name': name, 'icon': icon, 'status': 'available'}
            )
            categories[slug] = cat
        self.stdout.write(f'  ✅ {len(cats_data)} categories seeded')

        # ── Products ─────────────────────────────────────────────────
        products_data = [
            # (name, category_slug, desc, orig, price, stock, flowers, occasions, featured)
            ('Romantic Red Rose Bouquet',   'love',        'A classic bouquet of 50 premium red roses, elegantly wrapped in luxury satin.', 1299, 999,  15, 'rose', 'love anniversary', True),
            ('Sunshine Sunflower Bunch',    'birthday',    'Bright, cheerful sunflowers to light up any room and bring joy to the recipient.', 899, 699,  20, 'sunflower', 'birthday thank-you', True),
            ('Pink Garden Delight',         'anniversary', 'A garden-fresh mix of pink lilies, roses, and baby\'s breath in a kraft wrap.', 1599, 1299, 10, 'lily rose', 'anniversary love', True),
            ('White Wedding Elegance',      'wedding',     'A breathtaking arrangement of pure white orchids and lilies for your special day.', 2999, 2499, 8, 'orchid lily', 'wedding', True),
            ('Birthday Blast Bouquet',      'birthday',    'A colourful explosion of tulips and gerberas — the perfect birthday surprise!', 799, 599, 25, 'tulip', 'birthday', True),
            ('Lavender Love',               'love',        'Delicate lavender-hued tulips wrapped in soft pastel paper.', 999, 799, 18, 'tulip', 'love anniversary', False),
            ('Golden Anniversary Special',  'anniversary', 'Rich yellow roses and golden alstroemeria for a golden celebration.', 1899, 1499, 12, 'rose', 'anniversary', True),
            ('Sympathy White Lilies',       'sympathy',    'Peaceful white lilies in a minimalist arrangement to express heartfelt condolences.', 1199, 999, 10, 'lily', 'sympathy', False),
            ('Orchid Paradise',             'wedding',     'Exotic purple and white orchids arranged in a lush, tropical style.', 3499, 2999, 6, 'orchid', 'wedding anniversary', True),
            ('Thank You Sunburst',          'thank-you',   'A warm sunflower and gerbera mix to say thank you from the heart.', 699, 549, 22, 'sunflower', 'thank-you birthday', False),
            ('Cherry Blossom Dream',        'love',        'Delicate cherry blossom inspired bouquet with soft pink tones.', 1099, 899, 14, 'rose lily', 'love anniversary', False),
            ('Rainbow Tulip Mix',           'birthday',    'A vibrant rainbow of tulips in five different colours.', 899, 699, 30, 'tulip', 'birthday thank-you', False),
        ]
        count = 0
        for name, cat_slug, desc, orig, price, stock, flowers, occasions, featured in products_data:
            p, created = Product.objects.get_or_create(
                name=name,
                defaults={
                    'category': categories.get(cat_slug, categories['love']),
                    'description': desc,
                    'original_price': orig,
                    'price': price,
                    'stock_quantity': stock,
                    'flowers': flowers,
                    'occasion_tags': occasions,
                    'is_featured': featured,
                    'status': 'available',
                }
            )
            if created:
                count += 1
        self.stdout.write(f'  ✅ {count} products seeded (of {len(products_data)} total)')

        # ── Coupons ──────────────────────────────────────────────────
        coupons_data = [
            ('BLOOM10', 10, 200, date.today() + timedelta(days=90)),
            ('BLOOM20', 20, 100, date.today() + timedelta(days=60)),
            ('WELCOME15', 15, 500, date.today() + timedelta(days=180)),
            ('ROSE50', 50, 50, date.today() + timedelta(days=30)),
        ]
        for code, pct, max_uses, expiry in coupons_data:
            Coupon.objects.get_or_create(
                code=code,
                defaults={'discount_percent': pct, 'max_uses': max_uses, 'expiry': expiry, 'is_active': True}
            )
        self.stdout.write(f'  ✅ {len(coupons_data)} coupons seeded  (BLOOM10, BLOOM20, WELCOME15, ROSE50)')

        # ── Delivery Zones ───────────────────────────────────────────
        zones_data = [
            ('Mumbai City',   '400', 40),
            ('Mumbai Suburb', '401', 55),
            ('Delhi NCR',     '110', 65),
            ('Bangalore',     '560', 60),
            ('Chennai',       '600', 70),
            ('Hyderabad',     '500', 65),
            ('Pune',          '411', 55),
            ('Free Zone',     '999', 0),
        ]
        for zone_name, prefix, charge in zones_data:
            DeliveryZone.objects.get_or_create(
                pincode_prefix=prefix,
                defaults={'zone_name': zone_name, 'delivery_charge': charge}
            )
        self.stdout.write(f'  ✅ {len(zones_data)} delivery zones seeded')

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('🌸 Seed complete! Run: python manage.py runserver'))
        self.stdout.write('')
        self.stdout.write('  🔑 Admin login:  admin@bloomify.com  /  admin123')
        self.stdout.write('  🔑 Staff login:  staff@bloomify.com  /  staff123')
        self.stdout.write('  🔑 User login:   demo@bloomify.com   /  demo123')
