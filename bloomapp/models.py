from datetime import datetime

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.templatetags.static import static
from django.utils import timezone
from django.utils.html import format_html

# ── Choice Constants ────────────────────────────────────────────────────────────
ROLE_CHOICES = [('user', 'User'), ('admin', 'Admin'), ('staff', 'Staff')]
STATUS_CHOICES = [('available', 'Available'), ('unavailable', 'Unavailable')]
ORDER_STATUS = [
    ('placed', 'Order Placed'),
    ('packed', 'Packed'),
    ('out_for_delivery', 'Out for Delivery'),
    ('delivered', 'Delivered'),
    ('cancelled', 'Cancelled'),
]
PAYMENT_MODE = [('online', 'Online (Razorpay)'), ('upi', 'UPI'), ('card', 'Card'), ('cod', 'Cash on Delivery')]
FLOWER_CHOICES = [
    ('rose', 'Rose'),
    ('lily', 'Lily'),
    ('tulip', 'Tulip'),
    ('sunflower', 'Sunflower'),
    ('orchid', 'Orchid'),
]
# Free-licensed demo photo for each flower (see photo_credits.json), used for custom bouquets.
BOUQUET_PHOTOS = {
    'rose': 'bloomapp/demo/products/romantic-red-rose-bouquet.jpg',
    'lily': 'bloomapp/demo/products/sympathy-white-lilies.jpg',
    'tulip': 'bloomapp/demo/products/rainbow-tulip-mix.jpg',
    'sunflower': 'bloomapp/demo/products/sunshine-sunflower-bunch.jpg',
    'orchid': 'bloomapp/demo/products/orchid-paradise.jpg',
}
WRAPPING_CHOICES = [
    ('classic', 'Classic White'),
    ('rustic', 'Rustic Kraft'),
    ('luxury', 'Luxury Satin'),
    ('minimal', 'Minimal Green'),
]


# ── User ────────────────────────────────────────────────────────────────────────
class UserManager(BaseUserManager):
    """Users log in with their email address instead of a username."""

    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError('An email address is required.')
        user = self.model(email=self.normalize_email(email).lower(), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault('role', 'user')
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('role', 'admin')
        extra_fields['is_staff'] = True
        extra_fields['is_superuser'] = True
        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    """
    Customer, staff member or admin.

    `role` controls access to the Bloomify admin panel (staff = orders only,
    admin = everything). `is_staff`/`is_superuser` control the built-in
    Django admin at /django-admin/.
    """

    username = None
    first_name = None
    last_name = None

    full_name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=15, blank=True, default='')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='user')
    created_at = models.DateTimeField(auto_now_add=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['full_name']

    objects = UserManager()

    def __str__(self):
        return self.full_name or self.email

    def get_full_name(self):
        return self.full_name

    def get_short_name(self):
        return self.full_name.split(' ')[0] if self.full_name else self.email

    def is_admin(self):
        return self.role == 'admin'

    def is_staff_member(self):
        return self.role in ['admin', 'staff']


# ── Saved Address ───────────────────────────────────────────────────────────────
class SavedAddress(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='addresses')
    label = models.CharField(max_length=50, default='Home')
    full_name = models.CharField(max_length=100)
    phone = models.CharField(max_length=15)
    address = models.TextField()
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    pincode = models.CharField(max_length=10)
    is_default = models.BooleanField(default=False)

    def __str__(self):
        return f'{self.label} – {self.user.full_name}'


# ── Category ────────────────────────────────────────────────────────────────────
class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    image = models.ImageField(upload_to='categories/', blank=True, null=True)
    icon = models.CharField(max_length=50, default='🌸')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='available')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'Categories'

    def __str__(self):
        return self.name


# ── Product ──────────────────────────────────────────────────────────────────────
class Product(models.Model):
    name = models.CharField(max_length=200)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='products')
    extra_categories = models.ManyToManyField(
        Category,
        related_name='extra_products',
        blank=True,
        verbose_name='Also show in categories',
        help_text='Select additional categories where this product should also appear.',
    )
    description = models.TextField(blank=True, default='')
    original_price = models.DecimalField(max_digits=10, decimal_places=2)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    stock_quantity = models.IntegerField(default=10)
    image_main = models.ImageField(upload_to='products/', blank=True, null=True)
    image_2 = models.ImageField(upload_to='products/', blank=True, null=True)
    image_3 = models.ImageField(upload_to='products/', blank=True, null=True)
    # Photo without an upload: a full URL, or a path to a static file shipped with the site
    # (used by the demo catalogue, e.g. 'bloomapp/demo/products/lavender-love.jpg').
    image_url = models.CharField(max_length=500, blank=True, default='')
    flowers = models.CharField(max_length=200, blank=True, default='')
    occasion_tags = models.CharField(max_length=200, blank=True, default='')
    is_featured = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='available')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    @property
    def discount_percent(self):
        if self.original_price and self.price and self.original_price > self.price:
            return int(((self.original_price - self.price) / self.original_price) * 100)
        return 0

    @property
    def is_in_stock(self):
        return self.stock_quantity > 0

    @property
    def avg_rating(self):
        reviews = self.reviews.all()
        if reviews:
            return round(sum(r.rating for r in reviews) / len(reviews), 1)
        return 0

    def photo_tag(self):
        if self.image_main or self.image_url:
            return format_html('<img src="{}" width="80"/>', self.get_image)
        return '—'

    @property
    def get_image(self):
        """Best available image URL for this product."""
        if self.image_main:
            return self.image_main.url
        if self.image_url:
            if self.image_url.startswith(('http://', 'https://', '/')):
                return self.image_url
            return static(self.image_url)
        return static('bloomapp/img/placeholder-bouquet.svg')


# ── Review ───────────────────────────────────────────────────────────────────────
class Review(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='reviews')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    rating = models.IntegerField(default=5)
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.user.full_name} → {self.product.name} ({self.rating}★)'


# ── Delivery Zone (Location-based charges) ─────────────────────────────────────
class DeliveryZone(models.Model):
    zone_name = models.CharField(max_length=100)
    pincode_prefix = models.CharField(max_length=6)
    delivery_charge = models.DecimalField(max_digits=8, decimal_places=2, default=50)

    def __str__(self):
        return f'{self.zone_name} ({self.pincode_prefix}*) – ₹{self.delivery_charge}'


# ── Delivery Slot ─────────────────────────────────────────────────────────────
class DeliverySlot(models.Model):
    date = models.DateField()
    slot_label = models.CharField(max_length=50)
    slot_start = models.TimeField()
    slot_end = models.TimeField()
    max_orders = models.IntegerField(default=10)
    booked_count = models.IntegerField(default=0)

    def __str__(self):
        return f'{self.date} | {self.slot_label}'

    @property
    def is_available(self):
        return self.booked_count < self.max_orders

    @property
    def slots_left(self):
        return self.max_orders - self.booked_count

    @property
    def has_started(self):
        """True once the slot's start time has passed (in the shop's time zone)."""
        start = timezone.make_aware(datetime.combine(self.date, self.slot_start))
        return start <= timezone.now()

    @property
    def is_bookable(self):
        return self.is_available and not self.has_started


# ── Coupon ────────────────────────────────────────────────────────────────────
class Coupon(models.Model):
    code = models.CharField(max_length=30, unique=True)
    discount_percent = models.IntegerField(default=10)
    max_uses = models.IntegerField(default=100)
    used_count = models.IntegerField(default=0)
    expiry = models.DateField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.code} – {self.discount_percent}% off'

    @property
    def is_valid(self):
        from django.utils import timezone

        today = timezone.now().date()
        return self.is_active and self.used_count < self.max_uses and self.expiry >= today


# ── Custom Bouquet ────────────────────────────────────────────────────────────
class CustomBouquet(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    flowers = models.CharField(max_length=200, default='rose')
    flower_count = models.IntegerField(default=12)
    wrapping = models.CharField(max_length=30, choices=WRAPPING_CHOICES, default='classic')
    message_card = models.TextField(blank=True, default='')
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.display_name} by {self.user.full_name if self.user else "Guest"}'

    @property
    def flower_label(self):
        return dict(FLOWER_CHOICES).get(self.flowers, self.flowers.title())

    @property
    def display_name(self):
        """How the bouquet is named in the cart, orders and emails: "Custom: Rose bouquet"."""
        return f'Custom: {self.flower_label} bouquet'

    @property
    def summary(self):
        stems = f'{self.flower_count} stem{"" if self.flower_count == 1 else "s"}'
        card = ' · message card' if self.message_card else ''
        return f'{stems} · {self.get_wrapping_display()} wrap{card}'

    @property
    def get_image(self):
        return static(BOUQUET_PHOTOS.get(self.flowers, 'bloomapp/img/placeholder-bouquet.svg'))


class LineItemDisplay:
    """Name and photo for a cart or order line, whether it is a product or a custom bouquet."""

    @property
    def display_name(self):
        if self.product:
            return self.product.name
        if self.custom_bouquet:
            return self.custom_bouquet.display_name
        return 'Bouquet'

    @property
    def image_url(self):
        if self.product:
            return self.product.get_image
        if self.custom_bouquet:
            return self.custom_bouquet.get_image
        return static('bloomapp/img/placeholder-bouquet.svg')


# ── Cart Item ─────────────────────────────────────────────────────────────────
class CartItem(LineItemDisplay, models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, null=True, blank=True)
    custom_bouquet = models.ForeignKey(CustomBouquet, on_delete=models.CASCADE, null=True, blank=True)
    quantity = models.IntegerField(default=1)
    added_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.user.full_name} – {self.display_name} x{self.quantity}'

    @property
    def unit_price(self):
        if self.product:
            return self.product.price
        elif self.custom_bouquet:
            return self.custom_bouquet.price
        return 0

    @property
    def subtotal(self):
        return self.unit_price * self.quantity


# ── Order ─────────────────────────────────────────────────────────────────────
class Order(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    full_name = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    address = models.TextField()
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    pincode = models.CharField(max_length=10)
    delivery_zone = models.ForeignKey(DeliveryZone, on_delete=models.SET_NULL, null=True, blank=True)
    delivery_charge = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    coupon = models.ForeignKey(Coupon, on_delete=models.SET_NULL, null=True, blank=True)
    discount_amount = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_mode = models.CharField(max_length=10, choices=PAYMENT_MODE, default='cod')
    status = models.CharField(max_length=20, choices=ORDER_STATUS, default='placed')
    delivery_slot = models.ForeignKey(DeliverySlot, on_delete=models.SET_NULL, null=True, blank=True)
    special_note = models.TextField(blank=True, default='')
    razorpay_order_id = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Order #{self.id} — {self.full_name}'

    @property
    def status_display(self):
        return dict(ORDER_STATUS).get(self.status, self.status)

    @property
    def is_paid(self):
        try:
            return self.payment.status == 'completed'
        except Payment.DoesNotExist:
            return False

    @property
    def status_step(self):
        steps = ['placed', 'packed', 'out_for_delivery', 'delivered']
        try:
            return steps.index(self.status)
        except ValueError:
            return 0


# ── Order Item ────────────────────────────────────────────────────────────────
class OrderItem(LineItemDisplay, models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, null=True, blank=True)
    custom_bouquet = models.ForeignKey(CustomBouquet, on_delete=models.CASCADE, null=True, blank=True)
    quantity = models.IntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    line_total = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f'{self.display_name} x{self.quantity}'


# ── Payment ───────────────────────────────────────────────────────────────────
class Payment(models.Model):
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='payment')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    mode = models.CharField(max_length=10, choices=PAYMENT_MODE)
    transaction_id = models.CharField(max_length=100, blank=True, default='')
    status = models.CharField(max_length=20, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'Payment for Order #{self.order.id}'


# ── Contact Message ───────────────────────────────────────────────────────────
class ContactMessage(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True, default='')
    subject = models.CharField(max_length=100)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.name} – {self.subject}'


# ── Wishlist ──────────────────────────────────────────────────────────────────
class Wishlist(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='wishlist_items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='wishlisted_by')
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'product')
        ordering = ['-added_at']

    def __str__(self):
        return f'{self.user.full_name} ♥ {self.product.name}'


# ── Newsletter Subscriber ─────────────────────────────────────────────────────
class NewsletterSubscriber(models.Model):
    email = models.EmailField(unique=True)
    subscribed_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.email
